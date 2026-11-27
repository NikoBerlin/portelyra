# Verwaltung der Leser (rc.380, #486) in Data -> "Assets pflegen" -> Transaktionen -> "Leser".
#
# Festlegung (09.11.2026): je Leser Version, Pruefsumme, ob er in diesem Portfolio "an Ihren Belegen geprueft" ist, Buchungen je Leser
# und je Art die Buchungen ohne Herkunft; dazu der Selbsttest auf Knopfdruck mit dem echten Datum. Ein Leser gilt je Portfolio fuer genau
# seinen Plugin-Code als geprueft; eine geaenderte Hilfsbibliothek (SDK, Host) ist nur ein Hinweis. In Datenraeumen vor rc.380 gelten die
# mitgelieferten Leser ueber den einmaligen Eintrag "Bestand bis rc.379" als geprueft. Das Wort "Pruefstand" meint in der Oberflaeche das
# aeltere "geprueft bis" je Leser und kommt hier deshalb nicht vor.
#
# Die Uebersicht wird erst gelesen, wenn der Reiter offen ist. Der Selbsttest laeuft als eigener Prozess
# (system2 mit wait = FALSE, Ergebnis als Datei im Sitzungsordner) und wird mit invalidateLater abgefragt - die Sitzung bleibt bedienbar.
#
# rc.381 (Festlegung 09.11.2026): Leser werden je Plugin (ein Institut mit allen seinen Lesern) und je Portfolio aktiviert; neue Portfolios
# beginnen ohne aktive Plugins, in vor rc.380 angelegten Portfolios sind die mitgelieferten einmalig ueber "Bestand bis rc.380" aktiv. Fremde Plugins
# kommen als ZIP-Datei: sicher entpacken, pruefen, Selbsttest samt Erzeuger; installiert wird nur, was ihn besteht. Installierte Plugins
# lassen sich wieder entfernen (die Dateien bleiben zur Nachvollziehbarkeit), mitgelieferte nur deaktivieren. Jeder Schreibschritt:
# Vorschau -> Haekchen genau fuer diese Vorschau (jede Eingabeaenderung verwirft sie) -> Schreiben mit Pruefwert der Vorschau -> Ergebnis.
# Die Pruefung einer ZIP ist ein einzelner Aufruf (bis etwa eine Minute) und laeuft deshalb mit withProgress im Vordergrund.
data_statement_readers_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^statement_reader_[a-z_]+$", code)) code <- "statement_reader_admin_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_statement_readers_error_v1", "error", "condition")))
}
data_statement_readers_error_text_v1 <- function(code) switch(as.character(code),
  statement_reader_check_portfolio_unknown = "Der Datenraum hat kein Portfolio oder mehrere; ob ein Leser an Ihren Belegen geprüft ist, gilt je Portfolio.",
  statement_reader_check_store_invalid = "Ob die Leser an Ihren Belegen geprüft sind, oder die Herkunft der Buchungen ließ sich nicht lesen. Buchungen sind davon nicht berührt.",
  statement_reader_admin_input_invalid = "Die Anfrage an die Verwaltung der Leser war ungültig.",
  statement_reader_admin_store_invalid = paste("Die Leser, ihre Aktivierung oder der Buchungsbestand ließen sich nicht lesen oder nicht festhalten.",
                                               "Buchungen sind davon nicht berührt."),
  statement_reader_admin_preview_stale = "Seit der Vorschau hat sich etwas geändert – bitte erneut prüfen.",
  statement_reader_admin_confirmation_required = "Bitte zuerst die Vorschau prüfen und das Kästchen setzen.",
  statement_reader_install_zip_invalid = "Die Datei ist kein lesbares ZIP-Archiv (Endung .zip und gültiger Inhalt nötig).",
  statement_reader_install_zip_unsafe = paste("Das ZIP-Archiv enthält eine Verknüpfung oder einen Pfad außerhalb des Plugin-Ordners;",
                                              "es wird deshalb nicht entpackt."),
  statement_reader_install_too_large = "Das ZIP-Archiv ist zu groß: erlaubt sind höchstens 10 MB gepackt, 20 MB entpackt und 300 Dateien.",
  statement_reader_install_manifest_invalid = "Das Manifest des Plugins (manifest.json) fehlt, ist ungültig oder unvollständig.",
  statement_reader_install_api_unsupported = "Das Plugin verlangt eine Schnittstellenstufe (api_minor), die diese Portelyra-Fassung nicht kennt.",
  statement_reader_install_plugin_id_taken = paste("Ein mitgeliefertes Plugin trägt dieselbe Kennung; ein mitgeliefertes Plugin lässt sich",
                                                   "nicht durch ein installiertes ersetzen."),
  statement_reader_install_reader_id_taken = "Ein Leser des Plugins trägt dieselbe Kennung wie ein Leser eines anderen Plugins.",
  statement_reader_install_generator_missing = paste("Mindestens ein Leser des Plugins hat keinen Erzeuger; jeder Leser eines installierten",
                                                     "Plugins braucht einen, damit der Selbsttest erfundene Belege prüfen kann."),
  statement_reader_install_domain_unsupported = paste("Fremde Plugins können vorerst nur Cash-, Wertpapier-, Devisen- und Krypto-Belege lesen;",
                                                      "Rewards und Erträgnisaufstellungen noch nicht."),
  statement_reader_install_selftest_failed = "Der Selbsttest des Plugins ist nicht bestanden; installiert wird nur ein Plugin, das ihn besteht.",
  statement_reader_remove_shipped = paste("Mitgelieferte Plugins lassen sich nicht entfernen, nur je Portfolio auf „nicht aktiv“ setzen;",
                                          "ein Update eines mitgelieferten Plugins nimmt „Zur vorigen Fassung“ zurück."),
  # Pakete und Updates mitgelieferter Plugins (#486 Schritt 3, Festlegung 16.11.2026)
  statement_reader_install_package_invalid = "Die Datei hat nicht den Aufbau eines Plugin-Pakets (package.json fehlt, ist ungültig oder passt nicht zu einem Leser).",
  statement_reader_install_package_file_mismatch = "Eine Datei des Pakets weicht von ihrer Prüfsumme in package.json ab oder fehlt; das Paket wurde verändert.",
  statement_reader_install_package_mismatch = "Kennung oder Version in package.json passen nicht zum Manifest des Plugins.",
  statement_reader_install_update_unsigned = paste("Ein Plugin mit der Kennung eines mitgelieferten Plugins ist ein Update; es wird nur mit",
                                                   "Portelyra-Signatur installiert. Unsignierte Plugins brauchen eine eigene Kennung."),
  statement_reader_install_update_not_newer = "Das Update ist nicht neuer als die mitgelieferte Fassung; es gilt die höhere.",
  statement_reader_update_signature_invalid = paste("Die Signatur eines installierten Updates gilt nicht (mehr); Portelyra nimmt dafür die",
                                                    "mitgelieferte Fassung."),
  statement_reader_revert_unavailable = "Es gibt keine vorige Fassung, zu der zurückgegangen werden kann; ein eigenes Plugin lässt sich „Entfernen“.",
  plugin_signature_untrusted = "Das Paket ist signiert, aber nicht mit einem Schlüssel von Portelyra.",
  plugin_signature_invalid = "Die Signatur passt nicht zum Inhalt des Pakets; es wurde nach dem Signieren verändert.",
  plugin_signature_tool_missing = "Die Signatur lässt sich nicht prüfen, weil ssh-keygen fehlt.",
  statement_reader_remove_unknown = "Dieses Plugin ist nicht (mehr) installiert.",
  statement_reader_incompatible = paste("Der Selbsttest mit dieser Portelyra-Fassung ist nicht bestanden. Das Plugin ist gesperrt, bis eine neue",
                                        "Fassung des Herausgebers installiert ist und den Selbsttest besteht."),
  statement_reader_inactive = "Der Leser ist in diesem Portfolio nicht aktiv.",
  statement_reader_selftest_timeout = "Der Selbsttest hat nach 20 Minuten kein Ergebnis geliefert und wird nicht weiter abgefragt.",
  statement_reader_isolation_unavailable = paste("Leser laufen nur abgeschottet; das braucht Linux ab Kernel 6.2 (Landlock). Auf diesem Rechner",
                                                 "lässt sich der Selbsttest deshalb nicht ausführen."),
  "Die Verwaltung der Leser meldet einen Grund, für den es noch keinen deutschen Text gibt.")
# Immer mit Code: der genaue Grund bleibt sichtbar, auch wenn der Text allgemein ist.
data_statement_readers_error_copy_v1 <- function(code) sprintf("%s (%s)", data_statement_readers_error_text_v1(code), as.character(code))

new_data_statement_readers_service_v1 <- function(project_root, context, cli_runner = NULL, background = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); shell <- Sys.which("sh"); cli <- file.path(root, "scripts", "desktop_statement_readers.py")
  space <- if (is.null(cli_runner)) runtime_data_space_path(context) else ""
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_statement_readers_abort_v1("statement_reader_admin_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  request <- function(extra) as.character(jsonlite::toJSON(c(list(context = payload, data_space_path = space), extra), auto_unbox = TRUE, null = "null", digits = NA))
  parse <- function(output, status = 0L) {
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || !identical(parsed$status, "completed") || !identical(as.integer(status), 0L))
      data_statement_readers_abort_v1(if (is.list(parsed) && is.character(parsed$code)) parsed$code else "statement_reader_admin_store_invalid")
    parsed$result
  }
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command), stdout = TRUE, stderr = FALSE, input = request(extra)))
    status <- attr(output, "status"); parse(output, if (is.null(status)) 0L else status)
  }
  # Hintergrundlauf: Anfrage als Datei, Ergebnis erst nach dem Ende des Prozesses unter result.json (mv) - eine halbe Zeile gibt es nie.
  launch <- if (is.list(background)) background else list(
    start = function(command, extra) {
      if (!nzchar(shell)) data_statement_readers_abort_v1("statement_reader_admin_store_invalid")
      directory <- tempfile("portelyra-leser-selbsttest-"); if (!dir.create(directory, mode = "0700")) data_statement_readers_abort_v1("statement_reader_admin_store_invalid")
      input <- file.path(directory, "request.json"); part <- file.path(directory, "result.part"); done <- file.path(directory, "result.json")
      writeLines(enc2utf8(request(extra)), input, useBytes = TRUE)
      inner <- paste(shQuote(python), "-B -E -s", shQuote(cli), command, "<", shQuote(input), ">", shQuote(part), "2>/dev/null;", "mv -f", shQuote(part), shQuote(done))
      system2(shell, c("-c", shQuote(inner)), wait = FALSE, stdout = FALSE, stderr = FALSE)
      list(directory = directory, result = done)
    },
    poll = function(handle) if (file.exists(handle$result)) readLines(handle$result, warn = FALSE, encoding = "UTF-8") else NULL,
    cleanup = function(handle) unlink(handle$directory, recursive = TRUE))
  checked <- function(result, valid) {
    if (!is.list(result) || isTRUE(result$canonical_write) || !isTRUE(valid(result))) data_statement_readers_abort_v1("statement_reader_admin_store_invalid")
    result
  }
  fingerprint <- function(value) is.character(value) && length(value) == 1L && nzchar(value)
  confirm <- function(confirmed) if (!isTRUE(confirmed)) data_statement_readers_abort_v1("statement_reader_admin_confirmation_required")
  structure(list(
    contract_version = "data_statement_readers_service_v1",
    overview = function() {
      result <- run("overview", list())
      if (!is.list(result) || !identical(result$contract_version, "statement_reader_overview_v1") || isTRUE(result$canonical_write) || !is.list(result$readers))
        data_statement_readers_abort_v1("statement_reader_admin_store_invalid")
      result
    },
    selftest_start = function() launch$start("selftest", list()),
    # NULL, solange der Lauf nicht fertig ist; danach der Bericht (oder ein Fehler mit Code). Der Sitzungsordner des Laufs wird geraeumt.
    selftest_poll = function(handle) {
      output <- launch$poll(handle)
      if (is.null(output)) return(NULL)
      on.exit(launch$cleanup(handle), add = TRUE)
      result <- parse(output)
      if (!is.list(result) || !identical(result$contract_version, "statement_reader_selftest_report_v1") || isTRUE(result$canonical_write) || !is.list(result$plugins))
        data_statement_readers_abort_v1("statement_reader_admin_store_invalid")
      result
    },
    selftest_cleanup = function(handle) launch$cleanup(handle),
    # Aktivierung je Plugin und Portfolio, Installieren aus einer ZIP-Datei, Entfernen installierter Plugins (rc.381). Jeder Schreibschritt
    # traegt den Pruefwert seiner Vorschau; ohne Bestaetigung geht keiner an die CLI.
    activation = function() checked(run("activation", list()),
      function(result) identical(result$contract_version, "statement_reader_activation_v1") && is.list(result$plugins) && is.list(result$portfolios)),
    activation_preview = function(changes) checked(run("activation-preview", list(changes = changes)),
      function(result) is.list(result$changes) && fingerprint(result$preview_fingerprint)),
    activation_apply = function(changes, preview_fingerprint, recorded_at_utc, confirmed) {
      confirm(confirmed)
      checked(run("activation-apply", list(changes = changes, preview_fingerprint = preview_fingerprint, confirmed = TRUE, recorded_at_utc = recorded_at_utc)),
              function(result) is.numeric(result$written_count))
    },
    install_preview = function(zip_path, file_name) checked(run("install-preview", list(zip_path = zip_path, file_name = file_name)),
      function(result) is.character(result$plugin_id) && is.logical(result$installable) && fingerprint(result$preview_fingerprint)),
    install_apply = function(zip_path, file_name, preview_fingerprint, recorded_at_utc, confirmed) {
      confirm(confirmed)
      checked(run("install-apply", list(zip_path = zip_path, file_name = file_name, preview_fingerprint = preview_fingerprint, confirmed = TRUE,
                                        recorded_at_utc = recorded_at_utc)), function(result) identical(result$status, "installed"))
    },
    # Zur vorigen Fassung (#486 Schritt 3): Update zuruecknehmen, die Aktivierung bleibt.
    revert_preview = function(plugin_id) checked(run("revert-preview", list(plugin_id = plugin_id)),
      function(result) identical(result$plugin_id, plugin_id) && fingerprint(result$preview_fingerprint)),
    revert_apply = function(plugin_id, preview_fingerprint, recorded_at_utc, confirmed) {
      confirm(confirmed)
      checked(run("revert-apply", list(plugin_id = plugin_id, preview_fingerprint = preview_fingerprint, confirmed = TRUE, recorded_at_utc = recorded_at_utc)),
              function(result) identical(result$status, "reverted"))
    },
    remove_preview = function(plugin_id) checked(run("remove-preview", list(plugin_id = plugin_id)),
      function(result) identical(result$plugin_id, plugin_id) && fingerprint(result$preview_fingerprint)),
    remove_apply = function(plugin_id, preview_fingerprint, recorded_at_utc, confirmed) {
      confirm(confirmed)
      checked(run("remove-apply", list(plugin_id = plugin_id, preview_fingerprint = preview_fingerprint, confirmed = TRUE, recorded_at_utc = recorded_at_utc)),
              function(result) identical(result$status, "removed"))
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_statement_readers_service_v1", "list"))
}

DATA_STATEMENT_READERS_DOMAINS_V1 <- c(cash = "Cash", securities = "Wertpapiere", fx = "Devisen", crypto = "Krypto", reward = "Rewards",
  income_statement = "Erträgnisaufstellung")
DATA_STATEMENT_READERS_PROBLEMS_V1 <- c(statement_reader_manifest_invalid = "Manifest ungültig oder unvollständig",
  statement_reader_id_conflict = "Kennung eines Lesers ist schon vergeben", statement_reader_api_version_unsupported = "Schnittstellenversion nicht unterstützt",
  statement_reader_entry_mismatch = "Prüfsumme stimmt nicht mit dem Manifest überein (Datei verändert)",
  statement_reader_fixture_missing = "Testbeleg fehlt", statement_reader_unavailable = "nicht verfügbar")
DATA_STATEMENT_READERS_STAGES_V1 <- c(fixtures = "Testbelege", order = "Reihenfolge", mutations = "Veränderte Belege", generated = "Erfundene Belege")
DATA_STATEMENT_READERS_FINDINGS_V1 <- c(two_fresh_processes_differ = "zwei frische Läufe verschieden", expected_mismatch = "Ergebnis weicht von der Erwartung ab",
  malformed_result = "Ergebnis in ungültiger Form", depends_on_earlier_documents = "hängt von früheren Belegen ab", crash = "Absturz",
  timeout = "Zeitgrenze überschritten", foreign_code = "unbekannter Fehlercode", generator_invalid = "Erzeuger ungültig", generator_failed = "Erzeuger gescheitert",
  detection_rules_not_met = "erfüllt die Erkennungsregeln nicht", core_rejects = "vom Kern abgewiesen", generator_not_repeatable = "Erzeuger nicht wiederholbar")
DATA_STATEMENT_READERS_ORIGINS_V1 <- c(shipped = "mitgeliefert", installed = "installiert")
# Installierte Plugins testet Portelyra nach jedem Update neu (Festlegung 09.11.2026); mitgelieferte tragen "shipped".
DATA_STATEMENT_READERS_COMPATIBILITY_V1 <- c(compatible = "nach dem Update geprüft: bestanden",
  incompatible = "nach dem Update geprüft: nicht bestanden – gesperrt, bis eine neue Fassung des Herausgebers installiert ist und besteht",
  untested = "nach dem Update noch nicht geprüft")

data_statement_readers_ui_v1 <- function() shiny::tagList(
  portelyra_card("Leser", help = "app-data#leser",
    copy = "Jeder Import liest Belege mit einem Leser. Hier steht je Leser, in welcher Version er läuft, ob er in diesem Portfolio an Ihren Belegen geprüft ist und wie viele Buchungen er erzeugt hat.",
    note = portelyra_note_v1(title = "So lesen Sie die Tabelle", id = "data-statement-readers",
      "„An Ihren Belegen geprüft“ gilt je Portfolio und für genau den Code des Lesers (Prüfsumme über seine eigenen Dateien). Bestätigt wird es beim Buchen: Ist ein Leser noch nicht geprüft, verlangt die Vorschau ein zusätzliches Häkchen.",
      "Eine neue Version ist wieder ungeprüft, bis Sie eine Buchung damit bestätigen. Eine geänderte gemeinsame Hilfsbibliothek der Leser ist nur ein Hinweis.",
      "„Bestand bis rc.379“: In Datenräumen aus der Zeit vor rc.380 gelten die mitgelieferten Leser einmalig als geprüft – mit ihnen sind die dortigen Buchungen entstanden.",
      "Nicht zu verwechseln mit dem Prüfdatum im Import: Das ist der Tag, an dem das Format eines Lesers zuletzt an echten Belegen geprüft wurde.",
      "„davon mit jetzigem Code“ zählt die Buchungen, die genau der heute installierte Code samt Hilfsbibliothek erzeugt hat."),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_statement_readers_refresh", "Neu lesen", class = "btn-default")),
    shiny::uiOutput("data_statement_readers_state"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("data_statement_readers_table")),
    shiny::uiOutput("data_statement_readers_others"),
    shiny::uiOutput("data_statement_readers_problems"),
    shiny::h4(class = "pl-section-title", "Buchungen ohne Herkunft"),
    shiny::p(class = "pl-field-hint", paste("Ohne Herkunft sind Buchungen, die von Hand erfasst oder vor rc.378 importiert wurden. Sie bleiben gültig;",
      "welcher Leser sie erzeugt hat, ist für sie „nicht verfügbar“.")),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("data_statement_readers_kinds"))),
  portelyra_card("Aktivierung je Portfolio", help = "app-data#leser",
    copy = paste("Ein Plugin bringt alle Leser eines Instituts mit. Der Import bietet in einem Portfolio nur die Leser aktiver Plugins an;",
                 "mit einem nicht aktiven Plugin bucht der Kern nichts. Bereits vorhandene Buchungen bleiben in jedem Fall gültig."),
    note = portelyra_note_v1(title = "So funktioniert die Aktivierung", id = "data-statement-readers-activation",
      "Neue Portfolios beginnen ohne aktive Plugins. In Portfolios, die vor rc.380 angelegt wurden, sind die mitgelieferten Plugins einmalig über den Eintrag „Bestand bis rc.380“ aktiv.",
      "Häkchen setzen oder entfernen, dann „Änderungen prüfen“: Die Vorschau nennt genau die Änderungen; übernommen wird erst mit dem Kästchen darunter.",
      "Jede Änderung wird mit Datum festgehalten; frühere Stände bleiben erhalten. Ein installiertes Plugin ist nach dem Installieren in keinem Portfolio aktiv."),
    shiny::uiOutput("data_statement_readers_activation_table"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_statement_readers_activation_check", "Änderungen prüfen", class = "btn-default")),
    shiny::uiOutput("data_statement_readers_activation_preview"),
    shiny::uiOutput("data_statement_readers_activation_outcome")),
  # Installieren seit #486 Schritt 3 an einer Stelle fuer alle Plugins: Daten -> Einstellungen -> "Plugins" (Festlegung 16.11.2026).
  portelyra_card("Plugin installieren (ZIP)", help = "app-data#plugins-und-zugänge",
    copy = paste("Plugins – auch Updates der mitgelieferten Leser – installieren Sie unter Einstellungen → „Plugins und Zugänge“ → „Plugins“ → „Paket installieren“.",
                 "Dort wird ein Paket geprüft (Signatur, Selbsttest) und erst nach Ihrer Bestätigung installiert; aktiviert wird es hier.")),
  portelyra_card("Installierte Plugins: zurücknehmen oder entfernen", help = "app-data#plugins-und-zugänge",
    copy = paste("„Zur vorigen Fassung“ nimmt ein Update zurück – zur früher installierten oder zur mitgelieferten Fassung; die Aktivierung bleibt.",
                 "Ein entferntes Plugin wird nicht mehr geladen; seine Dateien bleiben im Datenraum, damit nachvollziehbar bleibt, womit gebucht",
                 "wurde. Buchungen bleiben unverändert. Mitgelieferte Plugins lassen sich nicht entfernen, nur je Portfolio auf „nicht aktiv“ setzen."),
    shiny::uiOutput("data_statement_readers_installed"),
    shiny::uiOutput("data_statement_readers_revert_preview"),
    shiny::uiOutput("data_statement_readers_revert_outcome"),
    shiny::uiOutput("data_statement_readers_remove_preview"),
    shiny::uiOutput("data_statement_readers_remove_outcome")),
  portelyra_card("Selbsttest der Leser", help = "app-data#leser",
    copy = paste("Prüft jeden Leser abgeschottet wie im Betrieb und mit dem Datum von heute: Testbelege genau und unabhängig von der Reihenfolge,",
                 "veränderte Belege ohne Absturz und ohne ungültiges Ergebnis, erfundene Belege aus dem Erzeuger genau. Liest keine Ihrer Belege und schreibt nichts."),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_statement_readers_selftest", "Selbsttest ausführen", class = "btn-default")),
    shiny::p(class = "pl-field-hint", "Dauert etwa 1–2 Minuten; Sie können währenddessen weiterarbeiten."),
    shiny::uiOutput("data_statement_readers_selftest_state"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("data_statement_readers_selftest_table"))))

.data_statement_readers_int_v1 <- function(value) if (is.numeric(value) && length(value) == 1L && !is.na(value)) as.integer(value) else 0L
.data_statement_readers_count_v1 <- function(value) pl_number_v1(.data_statement_readers_int_v1(value), 0L)

# "An Ihren Belegen geprueft" je Leser, mit dem Hinweis auf eine geaenderte Hilfsbibliothek.
data_statement_readers_check_text_v1 <- function(reader) {
  checked <- reader$checked; previous <- reader$previous
  text <- if (identical(reader$check_status, "checked") && is.list(checked)) {
    if (identical(checked$origin, "existing_data_space")) sprintf("Ja – Bestand bis rc.379 (%s)", pl_day_v1(checked$recorded_at_utc)) else {
      bookings <- checked$booking_count; documents <- checked$document_count
      counts <- if (is.null(bookings)) "" else if (is.null(documents)) sprintf(" (%d Buchungen)", as.integer(bookings)) else
        sprintf(" (%d Buchungen aus %d Belegen)", as.integer(bookings), as.integer(documents))
      paste0("Ja – bestätigt am ", pl_day_v1(checked$recorded_at_utc), counts)
    }
  } else if (is.list(previous)) {
    if (identical(as.character(previous$plugin_version), as.character(reader$plugin_version)))
      sprintf("Nein – Code geändert seit der Prüfung am %s (gleiche Version %s)", pl_day_v1(previous$recorded_at_utc), previous$plugin_version)
    else sprintf("Nein – neue Version seit Version %s (geprüft am %s)", previous$plugin_version, pl_day_v1(previous$recorded_at_utc))
  } else "Nein"
  if (isTRUE(reader$shared_changed)) paste0(text, " · Hilfsbibliothek seither geändert (nur Hinweis)") else text
}

# Nicht aktiv (rc.381): je Leser die Aktivierung seines Plugins je Portfolio; ohne Portfolio-Kennung zaehlt der einzige Eintrag.
.data_statement_readers_inactive_v1 <- function(reader, portfolio_id = NULL) {
  states <- reader$active
  if (!is.list(states) || !length(states)) return(FALSE)
  if (is.character(portfolio_id) && length(portfolio_id) == 1L) states <- Filter(function(state) identical(state$portfolio_id, portfolio_id), states)
  any(vapply(states, function(state) identical(state$active, FALSE), logical(1L)))
}
.data_statement_readers_with_active_v1 <- function(text, inactive) if (isTRUE(inactive)) paste0(text, " · nicht aktiv") else text

# Portfolios getrennt (Festlegung 09.11.2026): bei mehreren Portfolios je Portfolio eine Spalte "An Ihren Belegen geprüft".
data_statement_readers_portfolio_checks_v1 <- function(overview, readers) {
  portfolios <- if (is.list(overview)) overview$portfolios else list()
  if (length(portfolios) <= 1L) {
    single <- if (is.character(overview$portfolio_id)) overview$portfolio_id else if (length(portfolios)) portfolios[[1L]]$portfolio_id else NULL
    return(list(`An Ihren Belegen geprüft` = vapply(readers, function(row)
      .data_statement_readers_with_active_v1(data_statement_readers_check_text_v1(row), .data_statement_readers_inactive_v1(row, single)), character(1L))))
  }
  columns <- lapply(seq_along(portfolios), function(index) vapply(readers, function(row) {
    state <- if (length(row$checks) >= index) row$checks[[index]] else NULL
    text <- if (!is.list(state)) "–" else
      data_statement_readers_check_text_v1(list(check_status = state$status, checked = state$checked, previous = state$previous,
                                                shared_changed = state$shared_changed, plugin_version = row$plugin_version))
    .data_statement_readers_with_active_v1(text, .data_statement_readers_inactive_v1(row, portfolios[[index]]$portfolio_id))
  }, character(1L)))
  stats::setNames(columns, vapply(portfolios, function(item) paste0("Geprüft · ", as.character(item$label)), character(1L)))
}

# Herkunft je Leser; bei installierten Plugins dazu, ob sie den Selbsttest nach dem letzten Update bestanden haben.
data_statement_readers_origin_text_v1 <- function(reader) {
  origin <- pl_label_v1(DATA_STATEMENT_READERS_ORIGINS_V1, reader$origin)
  if (!identical(reader$origin, "installed") || !is.character(reader$compatibility) || !reader$compatibility %in% names(DATA_STATEMENT_READERS_COMPATIBILITY_V1)) return(origin)
  paste0(origin, " · ", unname(DATA_STATEMENT_READERS_COMPATIBILITY_V1[reader$compatibility]))
}

data_statement_readers_frame_v1 <- function(overview) {
  readers <- if (is.list(overview)) overview$readers else list()
  if (!length(readers)) return(data.frame())
  text <- function(value) if (is.character(value) && length(value) == 1L && nzchar(value)) value else "–"
  readers <- readers[order(vapply(readers, function(row) tolower(text(row$institution)), character(1L)), vapply(readers, function(row) tolower(text(row$label)), character(1L)))]
  head <- list(
    Institut = vapply(readers, function(row) text(row$institution), character(1L)),
    Leser = vapply(readers, function(row) text(row$label), character(1L)),
    Bereich = vapply(readers, function(row) pl_label_v1(DATA_STATEMENT_READERS_DOMAINS_V1, row$domain), character(1L)),
    Herkunft = vapply(readers, data_statement_readers_origin_text_v1, character(1L)),
    Version = vapply(readers, function(row) text(row$plugin_version), character(1L)),
    `Prüfsumme` = vapply(readers, function(row) { sha <- text(row$plugin_code_sha256); if (identical(sha, "–")) sha else substr(sha, 1L, 12L) }, character(1L)))
  tail <- list(
    `Buchungen mit Herkunft` = vapply(readers, function(row) .data_statement_readers_count_v1(row$bookings), character(1L)),
    `davon mit jetzigem Code` = vapply(readers, function(row) .data_statement_readers_count_v1(row$bookings_current_code), character(1L)),
    Erzeuger = vapply(readers, function(row) if (isTRUE(row$generator)) "ja" else "nein", character(1L)))
  as.data.frame(c(head, data_statement_readers_portfolio_checks_v1(overview, readers), tail), check.names = FALSE, stringsAsFactors = FALSE)
}

data_statement_readers_kinds_frame_v1 <- function(overview) {
  kinds <- if (is.list(overview)) overview$kinds else list()
  if (!length(kinds)) return(data.frame())
  data.frame(
    Art = vapply(kinds, function(row) as.character(row$label), character(1L)),
    Buchungen = vapply(kinds, function(row) .data_statement_readers_count_v1(row$total), character(1L)),
    `mit Herkunft` = vapply(kinds, function(row) .data_statement_readers_count_v1(row$with_provenance), character(1L)),
    `ohne Herkunft` = vapply(kinds, function(row) .data_statement_readers_count_v1(row$without_provenance), character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

data_statement_readers_summary_v1 <- function(overview, read_at_utc = NULL) {
  readers <- overview$readers; problems <- overview$problems
  # Bei mehreren Portfolios zaehlt ein Leser als geprueft, wenn er es in jedem Portfolio ist.
  checked <- sum(vapply(readers, function(row) if (length(row$checks) > 1L) all(vapply(row$checks, function(state) identical(state$status, "checked"), logical(1L)))
                                               else identical(row$check_status, "checked"), logical(1L)))
  plugins <- length(unique(vapply(readers, function(row) as.character(row$plugin_id), character(1L))))
  # Nach einem Update gesperrte installierte Plugins (rc.381) nennt die Zusammenfassung namentlich.
  blocked <- unique(unlist(lapply(readers, function(row) if (identical(row$compatibility, "incompatible"))
    paste0(if (is.character(row$institution)) row$institution else "–", " (", as.character(row$plugin_id), ")") else NULL)))
  copy <- sprintf("%d an Ihren Belegen geprüft, %d noch nicht an Ihren Belegen geprüft%s%s%s.", checked, length(readers) - checked,
                  if (length(problems)) sprintf(", %d Plugin%s verworfen", length(problems), if (length(problems) == 1L) "" else "s") else "",
                  if (length(blocked)) sprintf(", gesperrt nach dem Update (Selbsttest nicht bestanden): %s", paste(blocked, collapse = ", ")) else "",
                  if (is.null(read_at_utc)) "" else paste0(" · gelesen ", pl_moment_v1(read_at_utc)))
  list(title = sprintf("%d Leser in %d Plugins", length(readers), plugins), copy = copy, tone = if (length(problems) || length(blocked)) "warning" else "neutral")
}

# Leser mit Buchungen, die heute nicht (mehr) installiert sind, und der generische Leser im Kern.
data_statement_readers_others_v1 <- function(overview) {
  others <- if (is.list(overview)) overview$other_readers else list()
  if (!length(others)) return(NULL)
  items <- vapply(others, function(row) sprintf("%s: %s", if (identical(row$plugin_id, "portelyra_core")) paste0("Generischer Leser im Kern (", row$reader_id, ")") else
    paste0(row$reader_id, " (", row$plugin_id, ", nicht installiert)"), .data_statement_readers_count_v1(row$bookings)), character(1L))
  shiny::p(class = "pl-field-hint", paste0("Buchungen weiterer Leser – ", paste(items, collapse = " · "), "."))
}

data_statement_readers_problems_v1 <- function(overview) {
  problems <- if (is.list(overview)) overview$problems else list()
  if (!length(problems)) return(NULL)
  portelyra_status_panel(if (length(problems) == 1L) "1 Plugin verworfen" else sprintf("%d Plugins verworfen", length(problems)),
    shiny::tags$ul(lapply(problems, function(row) shiny::tags$li(sprintf("%s: %s (%s)", row$plugin_id,
      pl_label_v1(DATA_STATEMENT_READERS_PROBLEMS_V1, row$code), row$code)))), tone = "warning")
}

.data_statement_readers_duration_v1 <- function(seconds) {
  seconds <- if (is.numeric(seconds) && length(seconds) == 1L && !is.na(seconds)) round(seconds) else 0
  if (seconds < 60) sprintf("%d Sek.", as.integer(seconds)) else sprintf("%d Min. %d Sek.", as.integer(seconds %/% 60), as.integer(seconds %% 60))
}

# Ein Befund: Stufe – Befund (Code) × Zahl. Nie Belegnamen oder Inhalte.
.data_statement_readers_finding_text_v1 <- function(item) paste0(
  pl_label_v1(DATA_STATEMENT_READERS_STAGES_V1, item$stage), " – ", pl_label_v1(DATA_STATEMENT_READERS_FINDINGS_V1, item$finding),
  if (is.null(item$code)) "" else paste0(" (", item$code, ")"), " × ", .data_statement_readers_int_v1(item$count))

# Je Plugin eine Zeile: Ergebnis, Zaehlwerte und die Befunde je Stufe (Zahl, nie Inhalte).
data_statement_readers_selftest_frame_v1 <- function(report) {
  plugins <- if (is.list(report)) report$plugins else list()
  if (!length(plugins)) return(data.frame())
  total <- function(plugin, field) sum(vapply(plugin$readers, function(row) .data_statement_readers_int_v1(row[[field]]), integer(1L)))
  findings <- function(plugin) {
    several <- length(plugin$readers) > 1L
    items <- unlist(lapply(plugin$readers, function(row) vapply(row$findings, function(item) paste0(
      if (several) paste0(if (is.null(row$label)) row$reader_id else row$label, ": ") else "", .data_statement_readers_finding_text_v1(item)),
      character(1L))), use.names = FALSE)
    if (length(items)) paste(items, collapse = "; ") else "–"
  }
  data.frame(
    Institut = vapply(plugins, function(plugin) if (is.character(plugin$institution)) plugin$institution else "–", character(1L)),
    Plugin = vapply(plugins, function(plugin) as.character(plugin$plugin_id), character(1L)),
    Version = vapply(plugins, function(plugin) if (is.character(plugin$plugin_version)) plugin$plugin_version else "–", character(1L)),
    Ergebnis = vapply(plugins, function(plugin) if (length(plugin$problems)) paste0("verworfen (", paste(unlist(plugin$problems), collapse = ", "), ")") else
      if (isTRUE(plugin$passed)) "bestanden" else "nicht bestanden", character(1L)),
    Testbelege = vapply(plugins, function(plugin) pl_number_v1(total(plugin, "fixtures"), 0L), character(1L)),
    `davon unplausibel heute` = vapply(plugins, function(plugin) pl_number_v1(total(plugin, "implausible_today"), 0L), character(1L)),
    `Veränderte Belege` = vapply(plugins, function(plugin) pl_number_v1(total(plugin, "mutations"), 0L), character(1L)),
    `Erfundene Belege` = vapply(plugins, function(plugin) if (!any(vapply(plugin$readers, function(row) !is.null(row$generated), logical(1L)))) "kein Erzeuger" else
      pl_number_v1(total(plugin, "generated"), 0L), character(1L)),
    Befunde = vapply(plugins, findings, character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

data_statement_readers_selftest_summary_v1 <- function(report) {
  plugins <- report$plugins; failed <- sum(!vapply(plugins, function(plugin) isTRUE(plugin$passed), logical(1L)))
  readers <- unlist(lapply(plugins, function(plugin) plugin$readers), recursive = FALSE)
  count <- function(field) pl_number_v1(sum(vapply(readers, function(row) .data_statement_readers_int_v1(row[[field]]), integer(1L))), 0L)
  copy <- sprintf(paste("Gelaufen am %s, Dauer %s, mit dem Datum von heute (%s): %d Leser, %s Testbelege, %s veränderte und %s erfundene Belege.",
                        "Mitgelieferte Testbelege, die auf 2027 datiert sind, zählen heute nur als „unplausibel heute“ (%s), nicht als Fehler."),
                  pl_moment_v1(report$started_at_utc), .data_statement_readers_duration_v1(report$duration_seconds), pl_day_v1(report$reference_date),
                  length(readers), count("fixtures"), count("mutations"), count("generated"), count("implausible_today"))
  if (isTRUE(report$passed) && !failed) list(title = "Selbsttest bestanden", copy = copy, tone = "positive") else
    list(title = sprintf("Selbsttest: %d von %d Plugins nicht bestanden", failed, length(plugins)), copy = copy, tone = "error")
}

# ------------------------------------------------------------------ Aktivierung je Portfolio, Installieren, Entfernen (rc.381)
.data_statement_readers_text_v1 <- function(value) if (is.character(value) && length(value) == 1L && nzchar(value)) value else "–"
.data_statement_readers_state_word_v1 <- function(active) if (isTRUE(active)) "aktiv" else "nicht aktiv"
.data_statement_readers_quoted_v1 <- function(labels) paste(sprintf("„%s“", labels), collapse = ", ")
.data_statement_readers_outcome_ui_v1 <- function(outcome) if (is.list(outcome)) portelyra_status_panel(outcome$title, outcome$copy, tone = outcome$tone)
.data_statement_readers_error_outcome_v1 <- function(title, code) list(title = title, copy = data_statement_readers_error_copy_v1(code),
  tone = if (code %in% c("statement_reader_admin_preview_stale", "statement_reader_admin_confirmation_required")) "warning" else "error")
.data_statement_readers_loaded_v1 <- function(value) is.list(value) && is.null(attr(value, "code"))

# Eingabe-Kennungen: je Plugin (Zeile der sortierten Tabelle) und Portfolio (Reihenfolge der CLI) ein Kaestchen; je installiertem Plugin
# ein Knopf "Entfernen …". Die Zuordnung Zeile -> plugin_id haelt der Server aus genau der Liste, aus der er die Tabelle zeichnet.
data_statement_readers_active_input_id_v1 <- function(plugin_index, portfolio_index) sprintf("data_statement_readers_active_%d_%d", as.integer(plugin_index), as.integer(portfolio_index))
data_statement_readers_remove_input_id_v1 <- function(plugin_index) sprintf("data_statement_readers_remove_%d", as.integer(plugin_index))
data_statement_readers_revert_input_id_v1 <- function(plugin_index) sprintf("data_statement_readers_revert_%d", as.integer(plugin_index))

# Plugins sortiert wie die Uebersicht: Institut, Bezeichnung, Kennung.
data_statement_readers_activation_rows_v1 <- function(activation) {
  plugins <- if (.data_statement_readers_loaded_v1(activation)) activation$plugins else list()
  if (!length(plugins)) return(list())
  text <- .data_statement_readers_text_v1
  plugins[order(vapply(plugins, function(row) tolower(text(row$institution)), character(1L)), vapply(plugins, function(row) tolower(text(row$label)), character(1L)),
                vapply(plugins, function(row) text(row$plugin_id), character(1L)))]
}
data_statement_readers_installed_rows_v1 <- function(activation) Filter(function(row) identical(row$origin, "installed"), data_statement_readers_activation_rows_v1(activation))
.data_statement_readers_plugin_state_v1 <- function(plugin, portfolio_id) {
  for (state in plugin$states) if (identical(state$portfolio_id, portfolio_id)) return(state)
  NULL
}
data_statement_readers_activation_hint_v1 <- function(state, plugin_origin = NULL) {
  # Noch nie eingestellt (Festlegung 09.11.2026): ein mitgeliefertes Plugin, das ein Update neu mitbringt - getrennt von bewusst ausgeschalteten.
  if (is.list(state) && is.null(state$origin) && !isTRUE(state$active) && identical(plugin_origin, "shipped")) return("neu – noch nicht eingestellt")
  if (!is.list(state) || !is.character(state$origin)) return("")
  if (identical(state$origin, "existing_portfolio")) return("Bestand bis rc.380")
  if (identical(state$origin, "owner")) return(sprintf("%s seit %s", .data_statement_readers_state_word_v1(state$active), pl_day_v1(state$recorded_at_utc)))
  ""
}

# Gewuenschte Aenderungen: jedes Kaestchen, das vom gespeicherten Stand abweicht. Noch nicht gezeichnete Kaestchen (NULL) zaehlen nicht.
data_statement_readers_activation_changes_v1 <- function(activation, value_of) {
  rows <- data_statement_readers_activation_rows_v1(activation); portfolios <- if (.data_statement_readers_loaded_v1(activation)) activation$portfolios else list()
  changes <- list()
  for (plugin_index in seq_along(rows)) for (portfolio_index in seq_along(portfolios)) {
    chosen <- value_of(data_statement_readers_active_input_id_v1(plugin_index, portfolio_index))
    if (is.null(chosen)) next
    portfolio_id <- portfolios[[portfolio_index]]$portfolio_id
    if (!identical(isTRUE(chosen), isTRUE(.data_statement_readers_plugin_state_v1(rows[[plugin_index]], portfolio_id)$active)))
      changes[[length(changes) + 1L]] <- list(portfolio_id = portfolio_id, plugin_id = rows[[plugin_index]]$plugin_id, active = isTRUE(chosen))
  }
  changes
}

data_statement_readers_activation_ui_v1 <- function(activation) {
  if (is.null(activation)) return(NULL)
  if (!is.null(attr(activation, "code"))) return(portelyra_status_panel("Aktivierung nicht lesbar", data_statement_readers_error_copy_v1(attr(activation, "code")), tone = "warning"))
  portfolios <- activation$portfolios; rows <- data_statement_readers_activation_rows_v1(activation); text <- .data_statement_readers_text_v1
  if (!length(portfolios)) return(portelyra_status_panel("Kein Portfolio", "Aktivieren lässt sich ein Plugin erst, wenn ein Portfolio angelegt ist.", tone = "neutral"))
  if (!length(rows)) return(portelyra_status_panel("Kein Plugin geladen", "Es gibt kein Plugin, das sich aktivieren ließe.", tone = "warning"))
  cells <- lapply(seq_along(rows), function(plugin_index) {
    plugin <- rows[[plugin_index]]
    c(list(text(plugin$institution), text(plugin$label), pl_label_v1(DATA_STATEMENT_READERS_ORIGINS_V1, plugin$origin), text(plugin$plugin_version)),
      lapply(seq_along(portfolios), function(portfolio_index) {
        state <- .data_statement_readers_plugin_state_v1(plugin, portfolios[[portfolio_index]]$portfolio_id); hint <- data_statement_readers_activation_hint_v1(state, plugin$origin)
        shiny::tagList(
          shiny::checkboxInput(data_statement_readers_active_input_id_v1(plugin_index, portfolio_index), shiny::tagList("aktiv",
            shiny::span(class = "sr-only", sprintf(" – %s im Portfolio „%s“", text(plugin$label), text(portfolios[[portfolio_index]]$label)))), value = isTRUE(state$active)),
          if (nzchar(hint)) shiny::div(class = "pl-field-hint", hint))
      }))
  })
  shiny::div(class = "pl-table-wrap", pl_table_v1(c("Institut", "Plugin", "Herkunft", "Version",
    vapply(portfolios, function(item) sprintf("Portfolio „%s“", text(item$label)), character(1L))), cells))
}

data_statement_readers_change_text_v1 <- function(change) sprintf("%s im Portfolio „%s“: %s → %s", .data_statement_readers_text_v1(change$plugin_label),
  .data_statement_readers_text_v1(change$portfolio_label), .data_statement_readers_state_word_v1(change$from), .data_statement_readers_state_word_v1(change$to))

data_statement_readers_activation_preview_ui_v1 <- function(preview) {
  if (!is.list(preview)) return(NULL)
  changes <- preview$result$changes; unchanged <- .data_statement_readers_int_v1(preview$result$unchanged_count)
  skipped <- if (unchanged > 0L) shiny::p(class = "pl-field-hint", if (unchanged == 1L) "1 gewählte Änderung entspricht inzwischen schon dem gespeicherten Stand und entfällt." else
    sprintf("%d gewählte Änderungen entsprechen inzwischen schon dem gespeicherten Stand und entfallen.", unchanged))
  if (!length(changes)) return(shiny::tagList(portelyra_status_panel("Nichts zu ändern", "Die gewählten Häkchen entsprechen dem gespeicherten Stand.", tone = "neutral"), skipped))
  off <- Filter(function(change) identical(change$to, FALSE), changes)
  shiny::tagList(
    shiny::h4(class = "pl-section-title", if (length(changes) == 1L) "Vorschau: 1 Änderung" else sprintf("Vorschau: %d Änderungen", length(changes))),
    shiny::tags$ul(class = "pl-plain-list", lapply(changes, function(change) shiny::tags$li(data_statement_readers_change_text_v1(change)))),
    skipped,
    if (length(off)) portelyra_status_panel("Was „nicht aktiv“ bewirkt", paste0(
      paste(vapply(off, function(change) sprintf("%s in „%s“", .data_statement_readers_text_v1(change$plugin_label), .data_statement_readers_text_v1(change$portfolio_label)), character(1L)), collapse = ", "),
      ": Die Leser erscheinen dort nicht mehr in den Import-Karten, und der Kern bucht nichts mehr mit ihnen. Bereits vorhandene Buchungen bleiben unverändert gültig."), tone = "warning"),
    shiny::checkboxInput("data_statement_readers_activation_confirm", sprintf("Ich habe die Vorschau geprüft: genau %s übernehmen.",
      if (length(changes) == 1L) "diese Änderung" else sprintf("diese %d Änderungen", length(changes))), FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_statement_readers_activation_apply", "Übernehmen", class = "btn-primary")))
}

data_statement_readers_install_readers_frame_v1 <- function(readers) {
  if (!length(readers)) return(data.frame())
  text <- .data_statement_readers_text_v1
  data.frame(
    Leser = vapply(readers, function(row) text(row$label), character(1L)),
    Kennung = vapply(readers, function(row) text(row$reader_id), character(1L)),
    Bereich = vapply(readers, function(row) pl_label_v1(DATA_STATEMENT_READERS_DOMAINS_V1, row$domain), character(1L)),
    `Geprüfte Formate` = vapply(readers, function(row) { formats <- unlist(row$tested_formats, use.names = FALSE); if (length(formats)) paste(formats, collapse = " · ") else "nicht angegeben" }, character(1L)),
    `Bekannte Grenzen` = vapply(readers, function(row) { limits <- unlist(row$known_limits, use.names = FALSE); if (length(limits)) paste(limits, collapse = "; ") else "keine angegeben" }, character(1L)),
    Erzeuger = vapply(readers, function(row) if (isTRUE(row$generator)) "ja" else "nein", character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

# Selbsttest einer ZIP je Leser, mit denselben Befundtexten wie der Selbsttest aller Leser.
data_statement_readers_install_selftest_frame_v1 <- function(selftest, readers = list()) {
  rows <- if (is.list(selftest)) selftest$readers else list()
  if (!length(rows)) return(data.frame())
  labels <- stats::setNames(vapply(readers, function(row) .data_statement_readers_text_v1(row$label), character(1L)), vapply(readers, function(row) .data_statement_readers_text_v1(row$reader_id), character(1L)))
  count <- function(row, field) pl_number_v1(.data_statement_readers_int_v1(row[[field]]), 0L)
  data.frame(
    Leser = vapply(rows, function(row) { id <- .data_statement_readers_text_v1(row$reader_id); if (id %in% names(labels)) unname(labels[id]) else id }, character(1L)),
    Bereich = vapply(rows, function(row) pl_label_v1(DATA_STATEMENT_READERS_DOMAINS_V1, row$domain), character(1L)),
    Testbelege = vapply(rows, count, character(1L), "fixtures"),
    `davon unplausibel heute` = vapply(rows, count, character(1L), "implausible_today"),
    `Veränderte Belege` = vapply(rows, count, character(1L), "mutations"),
    `Erfundene Belege` = vapply(rows, count, character(1L), "generated"),
    Befunde = vapply(rows, function(row) if (length(row$findings)) paste(vapply(row$findings, .data_statement_readers_finding_text_v1, character(1L)), collapse = "; ") else "–", character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

data_statement_readers_problem_text_v1 <- function(code) {
  code <- as.character(code)
  text <- if (code %in% names(DATA_STATEMENT_READERS_PROBLEMS_V1)) unname(DATA_STATEMENT_READERS_PROBLEMS_V1[code]) else data_statement_readers_error_text_v1(code)
  sprintf("%s (%s)", text, code)
}

data_statement_readers_install_selftest_ui_v1 <- function(value) {
  selftest <- value$selftest
  if (!is.list(selftest)) return(portelyra_status_panel("Selbsttest nicht ausgeführt",
    "Er läuft erst, wenn Manifest, Schnittstellenstufe, Kennungen, Bereiche und Erzeuger in Ordnung sind – die Gründe stehen unten.", tone = "warning"))
  readers <- selftest$readers
  count <- function(field) pl_number_v1(sum(vapply(readers, function(row) .data_statement_readers_int_v1(row[[field]]), integer(1L))), 0L)
  problems <- unlist(selftest$problems, use.names = FALSE)
  copy <- sprintf("Dauer %s, mit dem Datum von heute: %d Leser, %s Testbelege (davon unplausibel heute %s), %s veränderte und %s erfundene Belege.%s",
                  .data_statement_readers_duration_v1(selftest$duration_seconds), length(readers), count("fixtures"), count("implausible_today"),
                  count("mutations"), count("generated"),
                  if (length(problems)) paste0(" Verworfen: ", paste(vapply(problems, data_statement_readers_problem_text_v1, character(1L)), collapse = "; "), ".") else "")
  shiny::tagList(
    portelyra_status_panel(if (isTRUE(selftest$passed)) "Selbsttest bestanden" else "Selbsttest nicht bestanden", copy, tone = if (isTRUE(selftest$passed)) "positive" else "error"),
    shiny::div(class = "pl-table-wrap", pl_frame_table_v1(data_statement_readers_install_selftest_frame_v1(selftest, value$readers))))
}

data_statement_readers_install_preview_ui_v1 <- function(preview) {
  if (!is.list(preview)) return(NULL)
  value <- preview$result; text <- .data_statement_readers_text_v1
  # Der Herausgeber ist eine Angabe im Manifest; "von Portelyra signiert" nur mit gueltiger Signatur eines Pakets (#486 Schritt 3).
  signed <- isTRUE(value$publisher_verified)
  publisher <- paste0(if (identical(text(value$publisher), "–")) "nicht angegeben" else value$publisher, " (laut Manifest) – ",
                      if (signed) "von Portelyra signiert" else "ungeprüft: nicht von Portelyra signiert")
  replaces <- value$replaces; shipped <- value$replaces_shipped
  facts <- list(
    c("Datei", text(preview$request$file_name)),
    c("Plugin", sprintf("%s (Kennung %s)", text(value$label), text(value$plugin_id))),
    c("Version", text(value$plugin_version)),
    c("Herausgeber", publisher),
    c("Institut", text(value$institution)),
    c("Schnittstellenstufe (api_minor)", if (is.numeric(value$api_minor) && length(value$api_minor) == 1L) as.character(as.integer(value$api_minor)) else "nicht angegeben"),
    c("Bisher", if (is.list(replaces)) sprintf("ersetzt die installierte Version %s", text(replaces$plugin_version)) else
      if (is.list(shipped)) sprintf("mitgelieferte Version %s – dieses Update löst sie ab", text(shipped$plugin_version)) else "nicht installiert – wird neu installiert"))
  problems <- unlist(value$problems, use.names = FALSE)
  shiny::tagList(
    shiny::h4(class = "pl-section-title", sprintf("Vorschau: „%s“ Version %s", text(value$label), text(value$plugin_version))),
    shiny::tags$ul(class = "pl-plain-list", lapply(facts, function(fact) shiny::tags$li(shiny::tags$strong(paste0(fact[[1L]], ": ")), fact[[2L]]))),
    shiny::div(class = "pl-table-wrap", pl_frame_table_v1(data_statement_readers_install_readers_frame_v1(value$readers))),
    data_statement_readers_install_selftest_ui_v1(value),
    if (length(problems)) portelyra_status_panel("Nicht installierbar", shiny::tags$ul(lapply(problems, function(code) shiny::tags$li(data_statement_readers_problem_text_v1(code)))), tone = "error"),
    if (!isTRUE(value$installable) && !length(problems)) portelyra_status_panel("Nicht installierbar", "Die Prüfung hat das Plugin nicht freigegeben, ohne einen Grund zu nennen.", tone = "error"),
    if (isTRUE(value$installable)) shiny::tagList(
      shiny::p(class = "pl-field-hint", if (is.list(replaces) || is.list(shipped)) paste("Die Aktivierung gilt je Plugin und bleibt deshalb, wie sie ist. An Ihren",
        "Belegen geprüft ist die neue Version erst, wenn Sie eine Buchung mit ihr bestätigen; „Zur vorigen Fassung“ nimmt sie zurück.") else
        "Installieren aktiviert das Plugin in keinem Portfolio; das geschieht danach in der Tabelle „Aktivierung je Portfolio“."),
      # Unsigniert: zusaetzliche Bestaetigung (Festlegung 15.11.2026: "ungeprueft" mit Selbsttest und Zusatzbestaetigung).
      if (!signed) shiny::checkboxInput("data_statement_readers_install_unchecked", paste("Ich weiß, dass Portelyra dieses Plugin nicht geprüft hat: Es liest",
        "meine Belege mit Code eines anderen Herausgebers. Ich installiere es trotzdem."), FALSE),
      shiny::checkboxInput("data_statement_readers_install_confirm", sprintf("Ich habe die Vorschau geprüft: „%s“ Version %s installieren.", text(value$label), text(value$plugin_version)), FALSE),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("data_statement_readers_install_apply", "Installieren", class = "btn-primary"))))
}

# Installierte Plugins mit "Aktiv in" und, aus der Uebersicht, ob sie nach dem letzten Update geprueft sind.
data_statement_readers_installed_ui_v1 <- function(activation, overview = NULL) {
  if (is.null(activation)) return(NULL)
  if (!is.null(attr(activation, "code"))) return(portelyra_status_panel("Installierte Plugins nicht verfügbar", data_statement_readers_error_copy_v1(attr(activation, "code")), tone = "warning"))
  rows <- data_statement_readers_installed_rows_v1(activation); text <- .data_statement_readers_text_v1
  if (!length(rows)) return(shiny::p(class = "pl-field-hint", "Es ist kein Plugin installiert."))
  readers <- if (.data_statement_readers_loaded_v1(overview)) overview$readers else list()
  checked <- function(plugin_id) {
    states <- unique(unlist(lapply(readers, function(row) if (identical(row$plugin_id, plugin_id)) row$compatibility else NULL), use.names = FALSE))
    states <- states[states %in% names(DATA_STATEMENT_READERS_COMPATIBILITY_V1)]
    if (!length(states)) return("nicht verfügbar")
    # Ein Plugin ist so gut wie sein schlechtester Leser.
    unname(DATA_STATEMENT_READERS_COMPATIBILITY_V1[c("incompatible", "untested", "compatible")[c("incompatible", "untested", "compatible") %in% states][[1L]]])
  }
  cells <- lapply(seq_along(rows), function(plugin_index) {
    plugin <- rows[[plugin_index]]
    labels <- unlist(lapply(activation$portfolios, function(portfolio) if (isTRUE(.data_statement_readers_plugin_state_v1(plugin, portfolio$portfolio_id)$active)) text(portfolio$label) else NULL))
    update <- !is.null(plugin$replaces_shipped)
    list(text(plugin$institution), text(plugin$label),
         if (update) sprintf("%s (Update der mitgelieferten %s)", text(plugin$plugin_version), text(plugin$replaces_shipped)) else text(plugin$plugin_version),
         if (length(labels)) .data_statement_readers_quoted_v1(labels) else "in keinem Portfolio", checked(plugin$plugin_id),
         shiny::tagList(
           shiny::actionButton(data_statement_readers_revert_input_id_v1(plugin_index), "Zur vorigen Fassung …", class = "btn-default btn-sm",
                               `aria-label` = sprintf("„%s“ zur vorigen Fassung …", text(plugin$label))),
           # Ein Update eines mitgelieferten Plugins wird nicht entfernt (das schaltete es ab), nur zurueckgenommen (#486 Schritt 3).
           if (!update) shiny::actionButton(data_statement_readers_remove_input_id_v1(plugin_index), "Entfernen …", class = "btn-default btn-sm",
                                            `aria-label` = sprintf("„%s“ entfernen …", text(plugin$label)))))
  })
  shiny::div(class = "pl-table-wrap", pl_table_v1(c("Institut", "Plugin", "Version", "Aktiv in", "Nach dem Update", "Aktion"), cells))
}

data_statement_readers_revert_preview_ui_v1 <- function(preview) {
  if (!is.list(preview)) return(NULL)
  value <- preview$result; text <- .data_statement_readers_text_v1
  target <- if (identical(value$to_origin, "shipped")) sprintf("die mitgelieferte Version %s", text(value$to_version)) else
    sprintf("die früher installierte Version %s", text(value$to_version))
  shiny::tagList(
    shiny::h4(class = "pl-section-title", sprintf("Vorschau: zur vorigen Fassung (Version %s → %s)", text(value$from_version), text(value$to_version))),
    shiny::tags$ul(class = "pl-plain-list",
      shiny::tags$li(sprintf("Danach gilt %s. Die Aktivierung je Portfolio bleibt, wie sie ist.", target)),
      shiny::tags$li("Buchungen bleiben unverändert; jede trägt die Fassung, mit der sie gelesen wurde. Die Dateien aller Fassungen bleiben im Datenraum.")),
    shiny::checkboxInput("data_statement_readers_revert_confirm", sprintf("Ich habe die Vorschau geprüft: zur Version %s zurück.", text(value$to_version)), FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_statement_readers_revert_apply", "Zur vorigen Fassung", class = "btn-primary")))
}

data_statement_readers_remove_preview_ui_v1 <- function(preview) {
  if (!is.list(preview)) return(NULL)
  value <- preview$result; text <- .data_statement_readers_text_v1
  active_in <- unlist(value$active_in, use.names = FALSE); bookings <- value$bookings_with_provenance
  booking_text <- if (!is.numeric(bookings) || length(bookings) != 1L || is.na(bookings))
    "Wie viele Buchungen seine Herkunft tragen, ist nicht verfügbar. Buchungen bleiben in jedem Fall unverändert gültig." else
    if (bookings == 0) "Keine Buchung trägt seine Herkunft." else if (bookings == 1) "1 Buchung trägt seine Herkunft; sie bleibt unverändert gültig." else
    sprintf("%s Buchungen tragen seine Herkunft; sie bleiben unverändert gültig.", pl_number_v1(bookings, 0L))
  shiny::tagList(
    shiny::h4(class = "pl-section-title", sprintf("Vorschau: „%s“ Version %s entfernen", text(value$label), text(value$plugin_version))),
    shiny::tags$ul(class = "pl-plain-list",
      shiny::tags$li(if (length(active_in)) sprintf("Aktiv in %s. Nach dem Entfernen bietet der Import seine Leser dort nicht mehr an.", .data_statement_readers_quoted_v1(active_in)) else
        "In keinem Portfolio aktiv."),
      shiny::tags$li(booking_text),
      shiny::tags$li("Die Dateien des Plugins bleiben im Datenraum, damit nachvollziehbar bleibt, womit gebucht wurde; geladen wird es danach nicht mehr.")),
    shiny::checkboxInput("data_statement_readers_remove_confirm", sprintf("Ich habe die Vorschau geprüft: „%s“ Version %s entfernen.", text(value$label), text(value$plugin_version)), FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_statement_readers_remove_apply", "Entfernen", class = "btn-primary")))
}

# Ein Schreibschritt: Vorschau, Haekchen genau fuer diese Vorschau, Ergebnis. Jede gezeigte Vorschau traegt eine eigene Nummer; das
# Haekchen zaehlt nur, wenn es nach dem Zeichnen genau dieser Vorschau gesetzt wurde (ein stehengebliebenes Haekchen einer frueheren
# Vorschau gilt nicht). Vorrang 10, damit Haekchen und Eingabeaenderungen vor einem Klick im selben Schub verarbeitet sind.
.data_statement_readers_flow_v1 <- function(input, confirm_id) {
  preview <- shiny::reactiveVal(NULL); outcome <- shiny::reactiveVal(NULL); confirmed <- shiny::reactiveVal(NULL); sequence <- 0L
  shiny::observeEvent(input[[confirm_id]], {
    current <- preview()
    confirmed(if (isTRUE(input[[confirm_id]]) && is.list(current)) current$sequence else NULL)
  }, ignoreInit = TRUE, priority = 10)
  list(preview = preview, outcome = outcome,
    show = function(request, result) { sequence <<- sequence + 1L; confirmed(NULL); outcome(NULL); preview(list(sequence = sequence, request = request, result = result)) },
    drop = function(value = NULL) { force(value); confirmed(NULL); preview(NULL); outcome(value) },   # force: value darf preview() lesen
    refuse = function() outcome(.data_statement_readers_error_outcome_v1("Noch nicht bestätigt", "statement_reader_admin_confirmation_required")),
    confirmed = function() {
      current <- shiny::isolate(preview())
      is.list(current) && isTRUE(shiny::isolate(input[[confirm_id]])) && identical(shiny::isolate(confirmed()), current$sequence)
    })
}

# 'active' sagt, ob der Reiter offen ist - erst dann wird gelesen, bei jedem Oeffnen neu (Buchungen aus dem Import zaehlen sofort mit).
data_statement_readers_server_v1 <- function(input, output, session, service, active = shiny::reactive(TRUE),
    now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), poll_ms = 2000L, timeout_seconds = 1200) {
  overview <- shiny::reactiveVal(NULL); read_at <- shiny::reactiveVal(NULL); activation <- shiny::reactiveVal(NULL)
  job <- shiny::reactiveVal(NULL); report <- shiny::reactiveVal(NULL); selftest_notice <- shiny::reactiveVal(NULL)
  failure <- function(error) structure(list(), code = if (is.character(error$code) && length(error$code) == 1L) error$code else "statement_reader_admin_store_invalid")
  code_of <- function(value) attr(value, "code")
  attempt <- function(expr) if (is.null(service)) structure(list(), code = "statement_reader_admin_store_invalid") else tryCatch(expr, error = failure)
  # Die Aktivierung wird mit der Uebersicht gelesen; ein gleicher Stand loest nichts aus (reactiveVal vergleicht), ein neuer verwirft Vorschauen.
  load_activation <- function() activation(attempt(service$activation()))
  read <- function() {
    value <- attempt(service$overview())
    overview(value); read_at(now_utc()); load_activation(); invisible(value)
  }
  shiny::observeEvent(active(), if (isTRUE(active())) read())
  shiny::observeEvent(input$data_statement_readers_refresh, read(), ignoreInit = TRUE)

  output$data_statement_readers_state <- shiny::renderUI({
    value <- overview()
    if (is.null(value)) return(NULL)
    if (!is.null(attr(value, "code"))) return(portelyra_status_panel("Leser nicht lesbar", data_statement_readers_error_copy_v1(attr(value, "code")), tone = "warning"))
    summary <- data_statement_readers_summary_v1(value, read_at())
    portelyra_status_panel(summary$title, summary$copy, tone = summary$tone)
  })
  output$data_statement_readers_table <- shiny::renderTable(data_statement_readers_frame_v1(overview()), striped = TRUE, spacing = "xs")
  output$data_statement_readers_others <- shiny::renderUI(data_statement_readers_others_v1(overview()))
  output$data_statement_readers_problems <- shiny::renderUI(data_statement_readers_problems_v1(overview()))
  output$data_statement_readers_kinds <- shiny::renderTable(data_statement_readers_kinds_frame_v1(overview()), striped = TRUE, spacing = "xs")

  # ---------------------------------------------------------------- Aktivierung je Portfolio
  activation_flow <- .data_statement_readers_flow_v1(input, "data_statement_readers_activation_confirm")
  install_flow <- .data_statement_readers_flow_v1(input, "data_statement_readers_install_confirm")
  remove_flow <- .data_statement_readers_flow_v1(input, "data_statement_readers_remove_confirm")
  revert_flow <- .data_statement_readers_flow_v1(input, "data_statement_readers_revert_confirm")
  stale_notice <- function(copy) list(tone = "neutral", title = "Vorschau verworfen", copy = copy)
  desired <- shiny::reactive(data_statement_readers_activation_changes_v1(activation(), function(id) input[[id]]))
  output$data_statement_readers_activation_table <- shiny::renderUI(data_statement_readers_activation_ui_v1(activation()))
  shiny::observeEvent(input$data_statement_readers_activation_check, {
    changes <- desired()
    if (!.data_statement_readers_loaded_v1(activation())) { activation_flow$drop(.data_statement_readers_error_outcome_v1("Vorschau nicht möglich",
      if (is.null(code_of(activation()))) "statement_reader_admin_store_invalid" else code_of(activation()))); return(invisible(NULL)) }
    if (!length(changes)) { activation_flow$drop(list(tone = "neutral", title = "Keine Änderung", copy = "Alle Häkchen entsprechen dem gespeicherten Stand.")); return(invisible(NULL)) }
    result <- attempt(service$activation_preview(changes))
    if (!is.null(code_of(result))) activation_flow$drop(.data_statement_readers_error_outcome_v1("Vorschau nicht möglich", code_of(result))) else activation_flow$show(changes, result)
  }, ignoreInit = TRUE)
  # Jede Aenderung an den Haekchen verwirft die Vorschau, ein neu gelesener Stand ebenso.
  shiny::observeEvent(desired(), {
    current <- activation_flow$preview()
    if (is.list(current) && !identical(current$request, desired())) activation_flow$drop(stale_notice("Die Häkchen haben sich seit der Vorschau geändert – bitte erneut prüfen."))
  }, ignoreInit = TRUE, priority = 10)
  shiny::observeEvent(activation(), {
    if (is.list(activation_flow$preview())) activation_flow$drop(stale_notice("Der gespeicherte Stand wurde neu gelesen – bitte erneut prüfen."))
    if (is.list(remove_flow$preview())) remove_flow$drop(stale_notice("Der Stand der Plugins wurde neu gelesen – bitte erneut prüfen."))
    if (is.list(revert_flow$preview())) revert_flow$drop(stale_notice("Der Stand der Plugins wurde neu gelesen – bitte erneut prüfen."))
  }, ignoreInit = TRUE, priority = 10)
  shiny::observeEvent(input$data_statement_readers_activation_apply, {
    current <- activation_flow$preview()
    if (!is.list(current) || !length(current$result$changes)) return(invisible(NULL))
    if (!activation_flow$confirmed()) { activation_flow$refuse(); return(invisible(NULL)) }
    result <- attempt(service$activation_apply(current$request, current$result$preview_fingerprint, now_utc(), TRUE))
    if (!is.null(code_of(result))) {
      activation_flow$drop(.data_statement_readers_error_outcome_v1("Nicht übernommen", code_of(result)))
      if (identical(code_of(result), "statement_reader_admin_preview_stale")) load_activation()
      return(invisible(NULL))
    }
    written <- .data_statement_readers_int_v1(result$written_count)
    activation_flow$drop(list(tone = "positive", title = "Übernommen",
      copy = shiny::tagList(sprintf("%s festgehalten am %s:", if (written == 1L) "1 Änderung" else sprintf("%d Änderungen", written), pl_moment_v1(now_utc())),
                            shiny::tags$ul(lapply(current$result$changes, function(change) shiny::tags$li(data_statement_readers_change_text_v1(change)))))))
    read()
  }, ignoreInit = TRUE)
  output$data_statement_readers_activation_preview <- shiny::renderUI(data_statement_readers_activation_preview_ui_v1(activation_flow$preview()))
  output$data_statement_readers_activation_outcome <- shiny::renderUI(.data_statement_readers_outcome_ui_v1(activation_flow$outcome()))

  # ---------------------------------------------------------------- Plugin installieren (ZIP)
  shiny::observeEvent(input$data_statement_readers_install_file, {
    install_flow$drop(if (is.list(install_flow$preview())) stale_notice("Eine andere Datei ist gewählt – bitte erneut prüfen.") else NULL)
  }, ignoreInit = TRUE, priority = 10)
  # Pruefen einer Plugin-ZIP; seit #486 Schritt 3 ruft sie das gemeinsame "Paket installieren" (Einstellungen -> "Plugins") auf.
  check_install <- function(request) {
    result <- shiny::withProgress(message = "Plugin wird geprüft", detail = "samt Selbsttest, bis zu etwa einer Minute", value = 0.3,
                                  attempt(service$install_preview(request$zip_path, request$file_name)))
    if (!is.null(code_of(result))) install_flow$drop(.data_statement_readers_error_outcome_v1("Prüfung nicht möglich", code_of(result))) else install_flow$show(request, result)
  }
  shiny::observeEvent(input$data_statement_readers_install_check, {
    file <- input$data_statement_readers_install_file
    if (is.null(file) || !length(file$datapath)) { install_flow$drop(list(tone = "warning", title = "Keine Datei gewählt", copy = "Bitte zuerst eine ZIP-Datei wählen.")); return(invisible(NULL)) }
    check_install(list(zip_path = as.character(file$datapath[[1L]]), file_name = enc2utf8(as.character(file$name[[1L]]))))
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$data_plugin_package_file, {
    if (is.list(install_flow$preview())) install_flow$drop(stale_notice("Eine andere Datei ist gewählt – bitte erneut prüfen."))
  }, ignoreInit = TRUE, priority = 10)
  shiny::observeEvent(input$data_statement_readers_install_apply, {
    current <- install_flow$preview()
    if (!is.list(current) || !isTRUE(current$result$installable)) return(invisible(NULL))
    if (!install_flow$confirmed()) { install_flow$refuse(); return(invisible(NULL)) }
    if (!isTRUE(current$result$publisher_verified) && !isTRUE(input$data_statement_readers_install_unchecked)) {
      install_flow$outcome(list(tone = "warning", title = "Noch nicht bestätigt", copy = paste("Dieses Plugin ist nicht von Portelyra signiert; bitte",
        "zusätzlich bestätigen, dass Sie es trotzdem installieren."))); return(invisible(NULL))
    }
    result <- shiny::withProgress(message = "Plugin wird installiert", detail = "der Selbsttest läuft dabei erneut", value = 0.3,
      attempt(service$install_apply(current$request$zip_path, current$request$file_name, current$result$preview_fingerprint, now_utc(), TRUE)))
    if (!is.null(code_of(result))) { install_flow$drop(.data_statement_readers_error_outcome_v1("Nicht installiert", code_of(result))); return(invisible(NULL)) }
    text <- .data_statement_readers_text_v1; replaces <- current$result$replaces
    install_flow$drop(list(tone = "positive", title = "Installiert", copy = if (is.list(replaces))
      sprintf("„%s“ Version %s ersetzt Version %s. Die Aktivierung je Portfolio gilt unverändert weiter.", text(current$result$label), text(result$plugin_version), text(replaces$plugin_version)) else
      sprintf("„%s“ Version %s ist installiert und in keinem Portfolio aktiv. Aktivieren Sie es in der Tabelle „Aktivierung je Portfolio“.", text(current$result$label), text(result$plugin_version))))
    read()
  }, ignoreInit = TRUE)
  output$data_statement_readers_install_preview <- shiny::renderUI(data_statement_readers_install_preview_ui_v1(install_flow$preview()))
  output$data_statement_readers_install_outcome <- shiny::renderUI(.data_statement_readers_outcome_ui_v1(install_flow$outcome()))

  # ---------------------------------------------------------------- Installierte Plugins entfernen
  installed <- shiny::reactive(data_statement_readers_installed_rows_v1(activation()))
  output$data_statement_readers_installed <- shiny::renderUI(data_statement_readers_installed_ui_v1(activation(), overview()))
  remove_preview <- function(position) {
    rows <- shiny::isolate(installed())
    if (position > length(rows)) return(invisible(NULL))
    plugin_id <- rows[[position]]$plugin_id
    result <- attempt(service$remove_preview(plugin_id))
    if (!is.null(code_of(result))) remove_flow$drop(.data_statement_readers_error_outcome_v1("Vorschau nicht möglich", code_of(result))) else remove_flow$show(list(plugin_id = plugin_id), result)
  }
  # Je Zeile ein Knopf; der Beobachter einer Zeile entsteht, sobald die Zeile das erste Mal gezeichnet wird, und liest beim Klick die
  # Liste, aus der gerade gezeichnet ist.
  remove_buttons <- new.env(parent = emptyenv())
  shiny::observe({
    for (position in seq_along(installed())) {
      id <- data_statement_readers_remove_input_id_v1(position)
      if (exists(id, envir = remove_buttons, inherits = FALSE)) next
      local({ row <- position; button <- id
        assign(button, shiny::observeEvent(input[[button]], remove_preview(row), ignoreInit = TRUE), envir = remove_buttons) })
    }
  })
  shiny::observeEvent(input$data_statement_readers_remove_apply, {
    current <- remove_flow$preview()
    if (!is.list(current)) return(invisible(NULL))
    if (!remove_flow$confirmed()) { remove_flow$refuse(); return(invisible(NULL)) }
    result <- attempt(service$remove_apply(current$request$plugin_id, current$result$preview_fingerprint, now_utc(), TRUE))
    if (!is.null(code_of(result))) { remove_flow$drop(.data_statement_readers_error_outcome_v1("Nicht entfernt", code_of(result))); return(invisible(NULL)) }
    text <- .data_statement_readers_text_v1
    remove_flow$drop(list(tone = "positive", title = "Entfernt", copy = sprintf(
      "„%s“ Version %s wird nicht mehr geladen. Seine Dateien bleiben im Datenraum; Buchungen mit seiner Herkunft bleiben unverändert.",
      text(current$result$label), text(current$result$plugin_version))))
    read()
  }, ignoreInit = TRUE)
  output$data_statement_readers_remove_preview <- shiny::renderUI(data_statement_readers_remove_preview_ui_v1(remove_flow$preview()))
  # Zur vorigen Fassung (#486 Schritt 3)
  revert_preview <- function(position) {
    rows <- shiny::isolate(installed())
    if (position > length(rows)) return(invisible(NULL))
    plugin_id <- rows[[position]]$plugin_id
    result <- attempt(service$revert_preview(plugin_id))
    if (!is.null(code_of(result))) revert_flow$drop(.data_statement_readers_error_outcome_v1("Vorschau nicht möglich", code_of(result))) else revert_flow$show(list(plugin_id = plugin_id), result)
  }
  revert_buttons <- new.env(parent = emptyenv())
  shiny::observe({
    for (position in seq_along(installed())) {
      id <- data_statement_readers_revert_input_id_v1(position)
      if (exists(id, envir = revert_buttons, inherits = FALSE)) next
      local({ row <- position; button <- id
        assign(button, shiny::observeEvent(input[[button]], revert_preview(row), ignoreInit = TRUE), envir = revert_buttons) })
    }
  })
  shiny::observeEvent(input$data_statement_readers_revert_apply, {
    current <- revert_flow$preview()
    if (!is.list(current)) return(invisible(NULL))
    if (!revert_flow$confirmed()) { revert_flow$refuse(); return(invisible(NULL)) }
    result <- attempt(service$revert_apply(current$request$plugin_id, current$result$preview_fingerprint, now_utc(), TRUE))
    if (!is.null(code_of(result))) { revert_flow$drop(.data_statement_readers_error_outcome_v1("Nicht zurückgenommen", code_of(result))); return(invisible(NULL)) }
    text <- .data_statement_readers_text_v1
    revert_flow$drop(list(tone = "positive", title = "Zurückgenommen", copy = sprintf("Es gilt jetzt Version %s%s. Die Aktivierung je Portfolio gilt unverändert weiter.",
      text(result$plugin_version), if (identical(result$origin, "shipped")) " (mitgeliefert)" else "")))
    read()
  }, ignoreInit = TRUE)
  output$data_statement_readers_revert_preview <- shiny::renderUI(data_statement_readers_revert_preview_ui_v1(revert_flow$preview()))
  output$data_statement_readers_revert_outcome <- shiny::renderUI(.data_statement_readers_outcome_ui_v1(revert_flow$outcome()))
  output$data_statement_readers_remove_outcome <- shiny::renderUI(.data_statement_readers_outcome_ui_v1(remove_flow$outcome()))

  # Selbsttest: hoechstens ein Lauf zugleich; der zweite Klick sagt, seit wann der erste laeuft.
  shiny::observeEvent(input$data_statement_readers_selftest, {
    current <- shiny::isolate(job())
    if (!is.null(current)) {
      selftest_notice(list(tone = "neutral", title = "Selbsttest läuft bereits", copy = sprintf("Gestartet %s; ein zweiter Lauf startet erst danach.", pl_moment_v1(current$started_at_utc))))
      return(invisible(NULL))
    }
    if (is.null(service)) { selftest_notice(list(tone = "warning", title = "Selbsttest nicht verfügbar", copy = data_statement_readers_error_copy_v1("statement_reader_admin_store_invalid"))); return(invisible(NULL)) }
    started_at_utc <- now_utc()
    handle <- tryCatch(service$selftest_start(), error = function(error) {
      selftest_notice(list(tone = "error", title = "Selbsttest nicht gestartet", copy = data_statement_readers_error_copy_v1(attr(failure(error), "code")))); NULL })
    if (is.null(handle)) return(invisible(NULL))
    selftest_notice(NULL); report(NULL)
    job(list(handle = handle, started_at_utc = started_at_utc, started = Sys.time()))
  }, ignoreInit = TRUE)
  shiny::observe({
    current <- job()
    if (is.null(current)) return(invisible(NULL))
    shiny::invalidateLater(poll_ms)
    result <- tryCatch(service$selftest_poll(current$handle), error = failure)
    if (is.null(result)) {
      if (as.numeric(difftime(Sys.time(), current$started, units = "secs")) > timeout_seconds) {
        try(service$selftest_cleanup(current$handle), silent = TRUE)
        job(NULL); selftest_notice(list(tone = "error", title = "Selbsttest ohne Ergebnis", copy = data_statement_readers_error_copy_v1("statement_reader_selftest_timeout")))
      }
      return(invisible(NULL))
    }
    job(NULL); selftest_notice(NULL)
    if (!is.null(attr(result, "code"))) selftest_notice(list(tone = "error", title = "Selbsttest ohne Ergebnis", copy = data_statement_readers_error_copy_v1(attr(result, "code"))))
    else report(result)
  })
  session$onSessionEnded(function() { current <- shiny::isolate(job()); if (!is.null(current) && !is.null(service)) try(service$selftest_cleanup(current$handle), silent = TRUE) })

  output$data_statement_readers_selftest_state <- shiny::renderUI({
    current <- job(); value <- report(); notice <- selftest_notice()
    shiny::tagList(
      if (!is.null(current)) portelyra_status_panel("Selbsttest läuft", sprintf("Läuft seit %s. Das Ergebnis erscheint hier, sobald er fertig ist.", pl_moment_v1(current$started_at_utc)), tone = "neutral"),
      if (!is.null(notice)) portelyra_status_panel(notice$title, notice$copy, tone = notice$tone),
      if (is.list(value)) { summary <- data_statement_readers_selftest_summary_v1(value); portelyra_status_panel(summary$title, summary$copy, tone = summary$tone) })
  })
  output$data_statement_readers_selftest_table <- shiny::renderTable(data_statement_readers_selftest_frame_v1(report()), striped = TRUE, spacing = "xs")
  invisible(list(read = read, overview = overview, job = job, report = report, activation = activation,
                 activation_flow = activation_flow, install_flow = install_flow, remove_flow = remove_flow, check_install = check_install))
}
