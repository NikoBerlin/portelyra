# Einrichtungsdialog vor dem ersten Start (#555): Fragen, Zusammenfassung, Uebernahme. Kern: migrations/reference/desktop_setup_v1.py,
# CLI scripts/desktop_setup.py, Vertrag contracts/desktop-setup/v1/.
#
# Festlegungen (12.11.2026): eigene Seite vor dem Start wie die Startseite des Passwortschutzes (eigener Prozess auf dem
# Port der Data-App, danach starten die Apps mit dem gewaehlten Umfang); Fragen in Alltagssprache, jede darf "spaeter" sein; Entwurf
# ohne Wirkung bis zur Bestaetigung; die gefuehrte Einrichtung je Portfolio in Data (#542) bleibt fuer weitere Portfolios.
# Uebernommen wird ueber dieselben Befehle wie die Karten: Datenraum anlegen, Katalog-Editor (Vorschau, Bestaetigung), Umfang (#542,
# Herkunft "setup"), Kursanbieter (Vorschau, Bestaetigung), Zeitplan "Von selbst aktualisieren", Passwortschutz (desktop_protection.py).
# Einen eigenen Schreibweg gibt es nicht.
#
# Ausbau b (rc.403): Kurse nur mit dem Baustein Marktdaten, mit den Hinweisen des Anbieters (Adressen, Kosten, Bedingungen) und ihrer
# Kenntnisnahme; der Zeitplan nur mit einem Kursanbieter und mit Zustimmung (wie die Karte); der Passwortschutz zuletzt. Das Passwort
# bleibt nur im Speicher dieser Sitzung, nie im Entwurf; der Wiederherstellungsschluessel erscheint genau einmal.
#
# Ausbau c (rc.404, Festlegungen 13.11.2026): Steuersatz ("weiss ich nicht" erlaubt) und Kirchensteuer mit Bundesland. Uebernommen ueber
# den Dienst der Steuer-App (Steuerbereich, Regelmodul je Projektionsart, Vorgabe je Asset-Typ, Angaben je Jahr, jeweils Vorschau und
# Bestaetigung) und einen ersten Run-Center-Lauf mit diesen Vorgaben - die bestaetigte Zusammenfassung gilt als seine Bestaetigung.
#
# Buchungsweg (#583, 0.3.4, Festlegung 26.11.2026): "Wie moechten Sie Buchungen erfassen?" nach "Was". "Von Hand" ist vorgewaehlt und
# gesperrt; "Aus Belegen und Auszuegen" schaltet den Baustein Belege (Import, Eingang, Ablage); die Schnittstelle (#544) steht ausgegraut.

# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
DESKTOP_SETUP_TEXT_V1 <- list(
  title = "Portelyra einrichten",
  questions = list(
    portfolio_name = list(title = "Wie soll Ihr Portfolio heißen?", label = "Name des Portfolios",
      copy = paste("Ein Portfolio ist ein eigener, getrennter Bestand – etwa je steuerliche Person. Weitere Portfolios legen Sie später in den",
                   "Einstellungen an; umbenennen geht dort jederzeit.")),
    base_currency = list(title = "In welcher Währung führen Sie es?", label = "Währung",
      copy = paste("Die Währung steht beim Anlegen fest. Die Steuerrechnung folgt deutschem Recht und rechnet in Euro.",
                   "Weitere Währungen folgen; bis dahin führt Portelyra Portfolios in Euro."),
      choices = c(EUR = "Euro (EUR)"),
      # Angezeigt, aber nicht waehlbar (Endabnahme 19.11.2026): noch nicht in allen Teilen geprueft.
      later_choices = c(CHF = "Schweizer Franken (CHF)", USD = "US-Dollar (USD)", GBP = "Britisches Pfund (GBP)"), later_note = "kommt später"),
    holdings = list(title = "Was möchten Sie erfassen?", label = "Mehrfachauswahl",
      copy = paste("Angeboten wird später, was Sie hier wählen. Abschalten löscht nichts, zuschalten geht jederzeit in den Einstellungen unter",
                   "„Umfang dieses Portfolios“."),
      choices = c(equity_etf = "Aktien und ETF", fund = "Fonds", bond = "Anleihen", crypto = "Krypto", commodity = "Edelmetalle und Rohstoffe",
                  derivative = "Derivate (Optionsscheine, Zertifikate)", other = "Sonstiges",
                  cash = "Bankkonten und Cash (Salden, Zinsen, Devisen)")),
    # Je Antwort ein Hinweis darunter; „Von Hand“ legt der Kern als immer gewaehlt fest (`fixed`). Die Schnittstelle steht ausgegraut wie
    # die weiteren Waehrungen.
    bookings = list(title = "Wie möchten Sie Buchungen erfassen?", label = "Mehrfachauswahl",
      copy = paste("Angeboten wird später, was Sie hier wählen. Abschalten löscht nichts, zuschalten geht jederzeit in den Einstellungen unter",
                   "„Umfang dieses Portfolios“."),
      choices = c(manual = "Von Hand: jede Buchung selbst eintragen",
                  documents = "Aus Belegen und Auszügen: Abrechnungen, Exporte und Kontoauszüge Ihrer Institute einlesen"),
      hints = c(manual = "Immer dabei – auch Korrektur und Storno laufen darüber.",
                documents = "Dazu gehören der Import mit den Lesern der Institute, der monatliche Eingang mit Belegordnern und die Belegablage."),
      later_choices = c(interface = "Per Schnittstelle: direkt bei Bank oder Broker abrufen"), later_note = "kommt später"),
    # Institute und Belegordner (#572 Teil d): nur mit „Aus Belegen und Auszuegen“; die Namen der Institute liefert der Kern (mitgelieferte
    # Leser). Der Belegordner ist freiwillig und wird an der Frage mit derselben Regel geprueft wie im Eingang.
    institutes = list(title = "Bei welchen Instituten haben Sie Konten?", label = "Institute mit Leser (Mehrfachauswahl)",
      copy = paste("Für diese Institute aktiviert Portelyra die Leser, die ihre Belege und Exporte einlesen. Weitere aktivieren Sie später in",
                   "Daten → „Leser“; Ihre Konten legen Sie in Daten an."),
      folder = "Belegordner (freiwillig)", folder_pick = "Ordner wählen …",
      folder_hint = paste("Ein Ordner außerhalb von Portelyra, in den Sie die Belege Ihrer Institute laden; Portelyra liest ihn nur. Leer lassen:",
                          "später im Eingang festlegen.")),
    purposes = list(title = "Wofür möchten Sie Portelyra nutzen?", label = "Mehrfachauswahl",
      copy = "Buchungen, Bestände, FIFO und realisierte Gewinne sind immer dabei. Was Sie jetzt nicht wählen, lässt sich jederzeit in den Einstellungen zuschalten – auch die Steuer.",
      choices = c(performance = "Wert und Entwicklung verfolgen: Kurse abrufen, Verlauf, Rendite",
                  tax = "Steuer: Jahresbericht und Steuerrechnung")),
    prices = list(title = "Woher sollen die Kurse kommen?", label = "Kursanbieter",
      copy = paste("Für Wert und Verlauf braucht Portelyra Kurse. Empfohlen für den Anfang: Yahoo Finance – kostenlos und ohne Schlüssel.",
                   "Weitere Anbieter lassen sich später in der App „Daten“ unter „Kursanbieter“ einschalten."),
      choices = c(yahoo = "Yahoo Finance: Kurse aus dem Netz abrufen", none = "Keinen Anbieter: Ich trage Kurse selbst ein oder nutze die Kurse meiner Buchungen"),
      terms = "Ich nehme die Hinweise und die Bedingungen des Anbieters zur Kenntnis.",
      none_note = paste("Ohne Anbieter bewertet Portelyra mit den Kursen Ihrer Buchungen oder mit eigenen Kursangaben. Einen Anbieter",
                        "schalten Sie später in Daten → „Kursanbieter“ zu.")),
    schedule = list(title = "Soll Portelyra von selbst aktualisieren?", label = "Zeitplan „Alles aktualisieren“",
      copy = paste("Ein Zeitgeber Ihres Systems startet zu den Uhrzeiten denselben Lauf wie der Knopf „Alles aktualisieren“ – auch wenn",
                   "Portelyra geschlossen ist. War der Rechner aus, holt er den Lauf beim nächsten Anmelden nach. Uhrzeiten ändern Sie in den",
                   "Einstellungen."),
      choices = c(manual = "Nein, ich klicke selbst auf „Alles aktualisieren“", daily = "Ja, täglich um 07:00 Uhr",
                  twice = "Ja, zweimal täglich um 07:00 und 19:00 Uhr"),
      consent = paste("Zustimmung: Zu den gewählten Uhrzeiten ruft Portelyra ohne mein Zutun Kurse beim Anbieter ab (nur lesend) und schreibt",
                      "Bewertungen, Tageshistorie, Snapshot, den Abschluss, die Momentaufnahme und die Datenbasis – wie",
                      "„Alles aktualisieren“.")),
    tax_rate = list(title = "Kennen Sie Ihren persönlichen Steuersatz?", label = "Persönlicher Steuersatz",
      copy = "Gemeint ist Ihr Grenzsteuersatz: der Satz, mit dem der nächste verdiente Euro besteuert wird.",
      # Kurz als Liste (Endabnahme 19.11.2026); %ORIENTIERUNG% setzt der Dialog aus apps/shared/tax_orientation_v1.csv ein.
      bullets = c("Er steht nicht im Steuerbescheid – Steuer geteilt durch Einkommen ergibt den niedrigeren Durchschnittssatz.",
                  "%ORIENTIERUNG%. Genau rechnet der Steuerrechner des Bundesfinanzministeriums.",
                  paste("Portelyra braucht ihn für Krypto und andere private Veräußerungen und für sonstige Einkünfte wie Staking;",
                        "Kapitalerträge rechnet es pauschal mit der Abgeltungsteuer."),
                  "Je Jahr änderbar in Daten → „Steuer“. Angaben ohne Gewähr, keine Steuer- oder Rechtsberatung."),
      choices = c(known = "Ja, mein Satz in Prozent:", unknown = "Weiß ich nicht"), value = "Satz in Prozent, etwa 35 oder 42"),
    church = list(title = "Zahlen Sie Kirchensteuer?", label = "Kirchensteuer",
      copy = "Der Satz hängt vom Bundesland ab: 8 % in Bayern und Baden-Württemberg, sonst 9 %. Je Jahr änderbar in Daten → „Steuer“.",
      choices = c(no = "Nein", yes = "Ja"), state = "Bundesland",
      states = c(BW = "Baden-Württemberg", BY = "Bayern", BE = "Berlin", BB = "Brandenburg", HB = "Bremen", HH = "Hamburg", HE = "Hessen",
                 MV = "Mecklenburg-Vorpommern", NI = "Niedersachsen", NW = "Nordrhein-Westfalen", RP = "Rheinland-Pfalz", SL = "Saarland",
                 SN = "Sachsen", ST = "Sachsen-Anhalt", SH = "Schleswig-Holstein", TH = "Thüringen")),
    protection = list(title = "Sollen Ihre Daten mit einem Passwort geschützt werden?", label = "Passwortschutz",
      copy = paste("Portelyra verschlüsselt dann Datenbestand und Backups. Ohne Passwort ist nichts lesbar, auch nicht in Kopien auf einer",
                   "Sicherungsplatte. Sie bekommen einmal einen Wiederherstellungsschlüssel, den Sie aufschreiben."),
      choices = c(yes = "Ja, mit einem Passwort schützen", no = "Nein, vorerst nicht (später in den Einstellungen)"),
      password = "Passwort (mindestens 10 Zeichen)", repeat_label = "Passwort wiederholen",
      keyring = "Mit der Anmeldung am Rechner entsperren (Passwort im Schlüsselbund)",
      keyring_hint = paste("Dann laufen Zeitpläne auch bei beendetem Portelyra, und der Start braucht kein Passwort, solange Sie am Rechner",
                           "angemeldet sind; nach dem Ruhezustand fragt Portelyra nach dem Passwort. Wer sich am Rechner automatisch ohne Passwort anmeldet, hebt",
                           "damit den Schutz faktisch auf."),
      understood = "Mir ist klar: Ohne Passwort und Wiederherstellungsschlüssel sind die Daten verloren.",
      stored = "Das Passwort ist für diese Sitzung hinterlegt. Zum Ändern neu eingeben, sonst die Felder leer lassen.",
      missing_tool = "Für den Passwortschutz fehlt auf diesem Rechner gocryptfs (Paket „gocryptfs“). Er lässt sich später in den Einstellungen einrichten."),
    # Update-Suche (#562, 0.3.3, Festlegung 25.11.2026): ohne Vorauswahl; %DATENSCHUTZ_UPDATES% ist der Hinweis aus
    # apps/shared/desktop_installation_v1.R (DESKTOP_UPDATE_PRIVACY_V1), derselbe wie in Data.
    updates = list(title = "Soll Portelyra nach neuen Versionen suchen?", label = "Neue Versionen",
      copy = "Portelyra kann selbst nachsehen, ob es eine neuere Version gibt, und es in jeder App links anzeigen. %DATENSCHUTZ_UPDATES%",
      choices = c(daily = "Ja, einmal am Tag automatisch suchen", manual = "Nein, nur wenn ich in den Einstellungen auf „Nach Updates suchen“ klicke"))),
  asset_types = c(equity = "Aktien", etf = "ETF", fund = "Fonds", bond = "Anleihen", derivative = "Derivate", crypto = "Krypto",
                  commodity = "Edelmetalle und Rohstoffe", cash = "Cash-Konten"),
  classifications = c(de_equity_share = "Aktie", de_fund = "Fonds", de_capital_instrument = "Kapitalinstrument",
                      de_private_disposal_asset = "privates Veräußerungsgut (Jahresfrist)", de_cash_interest = "Cash / Zinsen"),
  # Ohne den Baustein Belege: Ihn nennt die Zusammenfassung als „Gebucht wird“ (#583).
  modules = c(cash = "Cash", market_data = "Marktdaten (Kurse aus dem Netz)", history_analysis = "Verlauf und Analyse",
              tax_report = "Steuerbericht", tax_projection = "Steuerprojektion"),
  reasons = c(answer = "aus Ihrer Antwort", later = "„Später“ – vorerst alles an, abwählbar in den Einstellungen",
              default = "Vorgabe", without_prices = "rechnet nur mit Kursen sinnvoll; zuschaltbar, sobald Sie Kurse abrufen"),
  errors = c(
    desktop_setup_input_invalid = "Die Antworten passen nicht zusammen. Bitte mindestens eine Sache zum Erfassen wählen oder „Später“.",
    desktop_setup_state_invalid = "Der Entwurf der Einrichtung ist nicht lesbar. Bitte „Ohne Einrichtung starten“ und in der App „Daten“ einrichten.",
    desktop_setup_plan_stale = "Die Zusammenfassung gilt nicht mehr, weil sich etwas geändert hat. Bitte die neue Zusammenfassung prüfen.",
    desktop_setup_confirmation_required = "Bitte bestätigen, dass Sie die Zusammenfassung geprüft haben.",
    desktop_setup_folder_invalid = paste("Diesen Ordner kann Portelyra nicht als Belegordner nutzen: Er muss vorhanden sein, außerhalb des",
                                         "Datenbestands liegen und darf keine Verknüpfung sein. Oder das Feld leer lassen."),
    desktop_setup_password_missing = "Für den Passwortschutz fehlt das Passwort dieser Sitzung. Bitte bei der Frage zum Passwortschutz neu eingeben.",
    desktop_setup_apply_failed = "Ein Schritt ließ sich nicht ausführen."))

desktop_setup_message_v1 <- function(code) {
  text <- DESKTOP_SETUP_TEXT_V1$errors
  if (is.character(code) && length(code) == 1L && code %in% names(text)) return(text[[code]])
  if (exists("desktop_protection_message_v1", mode = "function") && is.character(code) && length(code) == 1L && startsWith(code, "desktop_protection_"))
    return(desktop_protection_message_v1(code))
  sprintf("Die Einrichtung meldet einen Fehler (%s).", as.character(code)[1L])
}

# Kern ueber eine Pipe (wie der Passwortschutz); `runner(command, payload)` ersetzt den Aufruf in Tests.
desktop_setup_cli_v1 <- function(project_root, command, payload = list(), runner = NULL) {
  if (is.function(runner)) return(runner(command, payload))
  python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "desktop_setup.py")
  if (!nzchar(python) || !file.exists(cli)) return(list(status = "blocked", code = "desktop_setup_state_invalid"))
  json <- as.character(jsonlite::toJSON(if (length(payload)) payload else structure(list(), names = character()), auto_unbox = TRUE,
                                        null = "null", digits = NA))
  output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command), stdout = TRUE, stderr = FALSE, input = json))
  parsed <- tryCatch(jsonlite::fromJSON(utils::tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(parsed) || !is.character(parsed$status)) list(status = "blocked", code = "desktop_setup_state_invalid") else parsed
}

# Kerndateien und Dienste, die die Uebernahme braucht - dieselben wie in der Data-App. In `envir` (Vorgabe: global).
# Hinweis vor der ersten Nutzung (Endabnahme 19.11.2026, #577): eine eigene Seite vor dem Einrichtungsdialog und vor dem Demo. Bestaetigt
# wird sie mit einem Haekchen; Portelyra merkt sich die Bestaetigung mit dem Abdruck genau dieses Textes im Programmordner und fragt bei
# einem geaenderten Text erneut. Wortlaut: Entwurf.
DESKTOP_FIRST_USE_NOTICE_V1 <- list(
  title = "Bevor Sie beginnen",
  items = c(
    "Portelyra ist eine Beta und freie Software – ohne Gewähr dafür, dass Ergebnisse richtig oder vollständig sind.",
    paste("Portelyra ist keine Anlage-, Steuer- oder Rechtsberatung. Steuerzahlen sind eine Modellrechnung; maßgeblich sind die Abrechnungen",
          "Ihrer Institute und Ihr Steuerbescheid."),
    "Portelyra rechnet mit dem, was Sie buchen oder einlesen. Pflege und Prüfung der Daten gegen Ihre Belege liegen bei Ihnen.",
    "Entscheidungen, die Sie auf Grundlage von Portelyra treffen, verantworten Sie selbst.",
    "Gewährleistung und Haftung sind nach der Lizenz (GNU AGPL, Abschnitte 15 und 16) ausgeschlossen, soweit das Gesetz es zulässt."),
  confirm = "Ich habe diese Hinweise gelesen und verstanden.", continue = "Weiter",
  missing = "Bitte bestätigen Sie zuerst, dass Sie die Hinweise gelesen haben.")

desktop_first_use_notice_fingerprint_v1 <- function() digest::digest(enc2utf8(paste(c(DESKTOP_FIRST_USE_NOTICE_V1$title, DESKTOP_FIRST_USE_NOTICE_V1$items),
                                                                                    collapse = "\n")), algo = "sha256", serialize = FALSE)

desktop_first_use_notice_path_v1 <- function(home) file.path(home, "first-use-notice.json")

desktop_first_use_notice_acknowledged_v1 <- function(home) {
  value <- tryCatch(jsonlite::fromJSON(desktop_first_use_notice_path_v1(home), simplifyVector = TRUE), error = function(error) NULL)
  is.list(value) && identical(value$text_sha256, desktop_first_use_notice_fingerprint_v1())
}

desktop_first_use_notice_acknowledge_v1 <- function(home, now = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
  path <- desktop_first_use_notice_path_v1(home); temporary <- paste0(path, ".tmp")
  writeLines(as.character(jsonlite::toJSON(list(contract_version = "desktop_first_use_notice_v1", text_sha256 = desktop_first_use_notice_fingerprint_v1(),
                                                acknowledged_at_utc = now), auto_unbox = TRUE)), temporary, useBytes = TRUE)
  Sys.chmod(temporary, "0600"); file.rename(temporary, path)
  invisible(desktop_first_use_notice_acknowledged_v1(home))
}

# Eckwerte des Einkommensteuertarifs zur Orientierung (rc.439, Festlegung 19.11.2026: bei Updates nachziehen, Jahr nennen). Eine Quelle:
# apps/shared/tax_orientation_v1.csv, je Jahr eine Zeile mit Fundstelle. Das Regelmodul rechnet keinen Tarif; die Werte sind nur
# Orientierung. Gilt das juengste Jahr nicht mehr, sagt der Text das; der Vertragstest verlangt vor einem oeffentlichen Release im neuen
# Jahr dessen Zeile.
desktop_tax_orientation_v1 <- function(project_root, today = Sys.Date()) {
  rows <- tryCatch(utils::read.csv(file.path(project_root, "apps", "shared", "tax_orientation_v1.csv"), colClasses = "character",
                                   stringsAsFactors = FALSE, encoding = "UTF-8"), error = function(error) NULL)
  if (!is.data.frame(rows) || !nrow(rows)) return(NULL)
  year <- format(as.Date(today), "%Y")
  rows <- rows[order(rows$year), , drop = FALSE]
  usable <- rows[rows$year <= year, , drop = FALSE]
  row <- if (nrow(usable)) usable[nrow(usable), ] else rows[1L, ]
  euro <- function(value) formatC(as.numeric(value), format = "d", big.mark = ".", decimal.mark = ",")
  list(year = row$year, current = identical(row$year, year), basic_allowance = euro(row$basic_allowance_eur),
       entry_rate = row$entry_rate_percent, rate_42_from = euro(row$rate_42_from_eur), rate_45_from = euro(row$rate_45_from_eur),
       source = row$source)
}

desktop_tax_orientation_text_v1 <- function(project_root, today = Sys.Date()) {
  values <- desktop_tax_orientation_v1(project_root, today)
  if (is.null(values)) return("Eckwerte des Tarifs nennt das Glossar der Hilfe")
  sprintf("Zur Orientierung %s%s je Person: bis %s € zu versteuerndem Einkommen 0 %%, danach ab %s %% steigend, 42 %% ab %s €, 45 %% ab %s €",
          values$year, if (isTRUE(values$current)) "" else " (neuere Werte sind noch nicht hinterlegt)", values$basic_allowance,
          values$entry_rate, values$rate_42_from, values$rate_45_from)
}

desktop_setup_load_v1 <- function(project_root, envir = .GlobalEnv) {
  for (file in c("runtime_context.R", "canonical_repository.R", "catalog_data_command.R", "desktop_product_runtime_v1.R"))
    sys.source(file.path(project_root, "packages", "spotcore", "R", file), envir = envir)
  # Die Huelle zuerst: Ihre Fehlertexte (pl_error_text_v1, #490) brauchen Zeitplan, Wiederherstellen und Demo auch hier.
  for (file in c(file.path("apps", "shared", "portelyra_ui_shell.R"), file.path("apps", "data", "desktop_catalog_editor_v1.R"),
                 file.path("apps", "data", "data_portfolio_configuration_v1.R"),
                 file.path("apps", "data", "data_price_providers_v1.R"), file.path("apps", "data", "data_refresh_all_store_v1.R"),
                 # Institute und Belegordner (#572): Leser-Aktivierung, Belegordner und Ordnerwahl wie in Data.
                 file.path("apps", "data", "data_statement_readers_v1.R"), file.path("apps", "data", "data_statement_archive_v1.R"),
                 file.path("apps", "data", "data_statement_intake_v1.R"),
                 file.path("apps", "data", "data_refresh_all_schedule_v1.R"), file.path("apps", "shared", "desktop_protection_v1.R"),
                 file.path("apps", "tax", "tax_ui_service_v1.R"), file.path("apps", "shared", "desktop_setup_restore_v1.R"),
                 file.path("apps", "shared", "desktop_demo_home_v1.R"), file.path("apps", "shared", "desktop_installation_v1.R")))
    sys.source(file.path(project_root, file), envir = envir)
  invisible(envir)
}

# Gibt es den Datenraum schon? Braucht nur Laufzeit und Kontext (das Startskript hat beides geladen), nicht den Katalog.
desktop_setup_data_space_present_v1 <- function(home) {
  runtime <- desktop_product_runtime_load_v1(home)
  file.exists(file.path(runtime_data_space_path(runtime$context), "canonical.sqlite"))
}

.desktop_setup_protected_v1 <- function(home) {
  path <- file.path(home, "protection.json")
  value <- if (file.exists(path)) tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(error) NULL) else NULL
  is.list(value) && isTRUE(value$enabled)
}

# Jetziger Stand fuer den Plan: gibt es den Datenraum, welche Portfolios, ist der Schutz schon an.
desktop_setup_current_v1 <- function(home) {
  present <- desktop_setup_data_space_present_v1(home)
  portfolios <- if (!present) list() else lapply(catalog_read_v1(desktop_product_runtime_load_v1(home)$context)$portfolios, function(row)
    list(label = as.character(row$display_name), status = as.character(row$status)))
  list(data_space = present, portfolios = portfolios, protection = .desktop_setup_protected_v1(home))
}

desktop_setup_status_v1 <- function(project_root, home, runner = NULL) {
  present <- tryCatch(desktop_setup_data_space_present_v1(home), error = function(error) NULL)
  if (!is.logical(present) || length(present) != 1L || is.na(present)) return(list(status = "blocked", code = "desktop_setup_state_invalid"))
  desktop_setup_cli_v1(project_root, "status", list(home = home, data_space_present = present), runner)
}

.desktop_setup_now_v1 <- function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")

.desktop_setup_fail_v1 <- function(code) stop(structure(class = c("spot_desktop_setup_error_v1", "error", "condition"),
                                                       list(message = code, call = NULL, code = code)))

# Dienste der Karten; Tests ersetzen sie (`services`): Kursanbieter und Zeitplan je Laufzeit, Passwortschutz als Aufruf des Kerns.
.desktop_setup_services_v1 <- function(project_root, home, services = list()) {
  defaults <- list(
    price_providers = function(runtime) new_data_price_providers_service_v1(project_root, runtime$context),
    # Institute und Belegordner (#572): wie die Karte „Aktivierung je Portfolio“ und „Als Belegordner festlegen“ im Eingang.
    readers = function(runtime) new_data_statement_readers_service_v1(project_root, runtime$context),
    intake_folder = function(runtime, folder, now) new_data_statement_archive_service_v1(project_root, runtime$context)$intake_folder(folder, now, TRUE),
    schedule = function(runtime) data_refresh_all_schedule_v1(project_root, runtime, data_refresh_all_store_v1(runtime_data_space_path(runtime$context))),
    protection = function(command, payload) desktop_protection_cli_v1(project_root, home, command, payload),
    # Wie die Data-App (desktop_product_app_v1.R: new_tax_ui_service_v1 mit dem Wurzelordner der Datenraeume).
    tax = function(runtime) new_tax_ui_service_v1(project_root, dirname(dirname(dirname(runtime_data_space_path(runtime$context)))),
                                                  list(tenant_id = runtime$context$tenant_id, user_id = runtime$context$user_id,
                                                       data_space_id = runtime$context$data_space_id)),
    # Erster Lauf im Run Center mit den Vorgaben des Dialogs - dieselben Aufrufe wie "Alles aktualisieren" (data_refresh_all_deps_v1.R).
    first_closing = function(runtime, portfolio_name, closing, now_utc) .desktop_setup_first_closing_v1(project_root, runtime, portfolio_name, closing, now_utc))
  utils::modifyList(defaults, services)
}

# Erster Run-Center-Lauf mit den Vorgaben des Dialogs (#555 c): Die bestaetigte Zusammenfassung gilt als Bestaetigung. Ohne Buchungen
# endet er "blockiert" (keine Bewertung) - "Alles aktualisieren" uebernimmt seine Eingaben trotzdem und erstellt den Abschluss, sobald
# Buchungen da sind (Probe 13.11.2026). Gibt es schon einen bestaetigten Lauf, bleibt er; hat das Portfolio schon Assets, entsteht keiner
# (deren Eingaben gehoeren in das Run Center).
.desktop_setup_first_closing_v1 <- function(project_root, runtime, portfolio_name, closing, now_utc) {
  ctx <- runtime$context
  center <- spotcore::new_desktop_run_center_v1()
  catalog <- spotcore::desktop_run_center_catalog_v1(center, ctx)
  today <- as.Date(substr(now_utc(), 1L, 10L))
  last <- spotcore::desktop_run_center_last_form_v1(center, ctx, as.character(today), format(today + 1L, "%Y-%m-%dT00:00:00Z"))
  if (!identical(last$status, "absent")) return("kept")
  if (length(Filter(function(asset) asset$asset_type != "cash" && identical(asset$status, "active"), catalog$assets))) return("skipped_assets")
  # Das Run Center fuehrt den Namen als `label` (desktop_run_center_catalog_v1), der Katalog als `display_name`.
  portfolio <- Filter(function(row) identical(row$label, portfolio_name) && identical(row$status, "active"), catalog$portfolios)
  if (!length(portfolio)) .desktop_setup_fail_v1("desktop_setup_apply_failed")
  form <- list(portfolio_ref = portfolio[[1L]]$ref, run_mode = closing$run_mode, as_of_date = as.character(today - 1L),
               cutoff_at_utc = format(today, "%Y-%m-%dT00:00:00Z"), tax_mode = closing$tax_mode, capital_income_tax_rate = NULL,
               personal_income_tax_rate = NULL, solidarity_surcharge_rate = NULL, church_tax_applicable = closing$church_tax_applicable,
               church_tax_rate = closing$church_tax_rate, fee_source = closing$fee_source, fee_fixed_decimal = NULL,
               fee_percentage_rate_decimal = NULL, asset_inputs = list(), grouping_mode = "none")
  preview <- spotcore::desktop_run_center_prepare_v1(center, ctx, form, now_utc(), runtime$data_space_label, NULL, NULL)
  issued <- now_utc()
  until <- format(as.POSIXct(issued, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") + 300, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  confirmation <- spotcore::desktop_run_center_build_confirmation_v1(center, ctx, preview, issued, until, project_root)
  result <- spotcore::desktop_run_center_execute_v1(center, ctx, preview, confirmation, issued, project_root)
  if (!isTRUE(result$status %in% c("completed", "blocked"))) .desktop_setup_fail_v1("desktop_setup_apply_failed")
  "recorded"
}

# Steuerschritt (#555 c) ueber den Dienst der Steuer-App, jeweils Vorschau und Bestaetigung wie in den Karten. Ein zweiter Versuch
# erkennt Vorhandenes (Regelmodul je Projektionsart, Vorgabe je Typ, Angaben je Jahr) und legt nichts doppelt an.
.desktop_setup_tax_v1 <- function(step, service, runtime, portfolio_name, now_utc) {
  tax <- service$tax(runtime)
  if (!isTRUE(tax$initialized())) invisible(tax$initialize())
  rows <- Filter(function(row) identical(row$display_name, portfolio_name) && identical(row$status, "active"), tax$catalog()$catalog$portfolios)
  if (!length(rows)) .desktop_setup_fail_v1("desktop_setup_apply_failed")
  ref <- rows[[1L]]$exchange_ref
  apply <- function(command, payload) { preview <- tax$preview(command, payload); invisible(tax$confirm_apply(preview$preview_ref, TRUE)) }
  overview <- tax$overview(ref, as.integer(substr(now_utc(), 1L, 4L)))
  for (mode in unlist(step$projection_modes)) {
    chosen <- Filter(function(row) identical(row$projection_mode, mode) && identical(row$plugin_id, step$plugin_id), overview$selections)
    if (!length(chosen)) apply("select_plugin", list(portfolio_ref = ref, projection_mode = mode, plugin_id = step$plugin_id,
                                                      effective_from = step$effective_from, status = "active"))
  }
  for (default in step$type_defaults) {
    present <- Filter(function(row) identical(row$asset_type, default$asset_type) && identical(row$classification_code, default$classification_code) &&
                        identical(as.integer(row$effective_from_year), as.integer(default$effective_from_year)), overview$asset_type_classifications)
    if (!length(present)) apply("set_asset_type_classification", list(portfolio_ref = ref, asset_type = default$asset_type,
      classification_code = default$classification_code, tax_bucket = default$tax_bucket,
      partial_exemption_rate_decimal = default$partial_exemption_rate_decimal, effective_from_year = as.integer(default$effective_from_year),
      effective_to_year = NULL))
  }
  for (year in unlist(step$years)) {
    current <- tax$overview(ref, as.integer(year))$parameters
    # Satz in rate_decimal, Betrag in amount_decimal, Kirchensteuer ja/nein in applicability_value (tax_ui_workspace_v1._parameter_public).
    value_of <- function(code) { hit <- Filter(function(row) identical(row$parameter_code, code), current)
      if (!length(hit)) return(NULL); row <- hit[[1L]]; as.character(row$rate_decimal %||% row$amount_decimal %||% row$applicability_value) }
    set <- function(code, value) if (!is.null(value) && !identical(value_of(code), value))
      apply("set_parameter", list(portfolio_ref = ref, tax_year = as.integer(year), parameter_code = code, currency = NULL, value_decimal = value))
    set("personal_income_tax_rate", step$personal_income_tax_rate)
    set("church_tax_applicable", step$church_tax_applicable)
    set("church_tax_rate", step$church_tax_rate)
  }
  "set"
}

# Fuehrt den bestaetigten Plan aus, Schritt fuer Schritt; der erste Fehler haelt an (der Entwurf bleibt, ein zweiter Versuch setzt fort:
# vorhandener Datenraum, gleichnamiges Portfolio, aktiver Anbieter und ein eingerichteter Schutz bleiben). Zurueck: je Schritt
# key/status(/code); der Wiederherstellungsschluessel haengt als Attribut "recovery_key" am Ergebnis, nie in den Ergebnissen selbst.
desktop_setup_apply_v1 <- function(project_root, home, plan, secrets = list(), now_utc = .desktop_setup_now_v1, services = list()) {
  service <- .desktop_setup_services_v1(project_root, home, services)
  state <- new.env(parent = emptyenv())
  state$runtime <- desktop_product_runtime_load_v1(home)
  state$portfolio_id <- NULL
  state$recovery_key <- NULL
  state$portfolio_name <- NULL
  find_portfolio <- function(name) {
    rows <- Filter(function(row) identical(row$display_name, name) && identical(row$status, "active"), catalog_read_v1(state$runtime$context)$portfolios)
    if (length(rows)) as.character(rows[[length(rows)]]$portfolio_id) else NULL
  }
  run_step <- function(step) {
    if (identical(step$action, "none")) return("skipped")
    if (identical(step$action, "keep") && identical(step$key, "protection")) return("kept")
    switch(step$key,
      data_space = {
        space <- runtime_data_space_path(state$runtime$context)
        if (file.exists(file.path(space, "canonical.sqlite"))) "kept" else {
          desktop_product_initialize_data_space_v1(state$runtime, file.path(project_root, "contracts"), now_utc(), "INITIALIZE_EMPTY_DATA_SPACE")
          state$runtime <- desktop_product_runtime_load_v1(home)
          "created"
        }
      },
      portfolio = {
        state$portfolio_name <- step$display_name
        existing <- find_portfolio(step$display_name)
        if (!is.null(existing)) { state$portfolio_id <- existing; "kept" } else {
          editor <- new_desktop_catalog_editor_v1(); context <- state$runtime$context
          invisible(desktop_catalog_editor_refresh_v1(editor, context))
          form <- list(action = "create", entity_type = "portfolio", entity_ref = "", portfolio_ref = "", display_name = step$display_name,
                       base_currency = step$base_currency, account_type = "", institution_label = "", asset_type = "", price_currency = "",
                       quantity_scale = "", valuation_method = "", isin = "")
          preview <- desktop_catalog_editor_prepare_v1(editor, context, form, now_utc())
          invisible(desktop_catalog_editor_execute_v1(editor, context, preview, TRUE))
          state$portfolio_id <- find_portfolio(step$display_name)
          if (is.null(state$portfolio_id)) .desktop_setup_fail_v1("desktop_setup_apply_failed")
          "created"
        }
      },
      scope = {
        if (is.null(state$portfolio_id)) .desktop_setup_fail_v1("desktop_setup_apply_failed")
        configuration <- new_data_portfolio_configuration_service_v1(project_root, state$runtime$context)
        invisible(configuration$read())
        preview <- configuration$preview(state$portfolio_id, step$configuration, origin = "setup")
        if (isTRUE(preview$unchanged)) "kept" else { invisible(configuration$apply(preview, TRUE)); "set" }
      },
      # Institute und Belegordner (#572): Die Leser der gewaehlten Institute fuer das eben angelegte Portfolio aktivieren (Vorschau, dann
      # Uebernehmen, wie die Karte), danach der Belegordner. Schon Aktives und ein gleicher Ordner bleiben; ein zweiter Versuch legt nichts
      # doppelt an.
      documents = {
        if (is.null(state$portfolio_id)) .desktop_setup_fail_v1("desktop_setup_apply_failed")
        changed <- FALSE
        wanted <- vapply(step$plugins, function(item) as.character(item$plugin_id), character(1L))
        if (length(wanted)) {
          readers <- service$readers(state$runtime)
          known <- readers$activation()$plugins
          active <- vapply(Filter(function(plugin) plugin$plugin_id %in% wanted, known), function(plugin)
            if (any(vapply(plugin$states, function(item) identical(item$portfolio_id, state$portfolio_id) && isTRUE(item$active), logical(1L))))
              as.character(plugin$plugin_id) else NA_character_, character(1L))
          missing <- setdiff(wanted, active[!is.na(active)])
          if (length(missing)) {
            changes <- lapply(missing, function(plugin_id) list(portfolio_id = state$portfolio_id, plugin_id = plugin_id, active = TRUE))
            preview <- readers$activation_preview(changes)
            invisible(readers$activation_apply(changes, preview$preview_fingerprint, now_utc(), TRUE))
            changed <- TRUE
          }
        }
        if (is.character(step$intake_folder) && length(step$intake_folder) == 1L && nzchar(step$intake_folder))
          changed <- identical(service$intake_folder(state$runtime, step$intake_folder, now_utc())$status, "recorded") || changed
        if (changed) "set" else "kept"
      },
      tax = {
        if (is.null(state$portfolio_name)) .desktop_setup_fail_v1("desktop_setup_apply_failed")
        .desktop_setup_tax_v1(step, service, state$runtime, state$portfolio_name, now_utc)
      },
      # Erster Abschluss, mit oder ohne Steuer (Festlegungen 13.11.2026): ein erster Lauf im Run Center mit den bestaetigten Vorgaben.
      closing = {
        if (is.null(state$portfolio_name)) .desktop_setup_fail_v1("desktop_setup_apply_failed")
        service$first_closing(state$runtime, state$portfolio_name, step, now_utc)
      },
      # Wie die Karte "Kursanbieter": Vorschau, dann Uebernehmen; die Kenntnisnahme der Bedingungen stand in der Frage.
      prices = {
        providers <- service$price_providers(state$runtime)
        preview <- providers$preview(step$provider_id, TRUE)
        if (!isTRUE(preview$changed)) "kept" else { invisible(providers$apply(preview, TRUE)); "activated" }
      },
      # Wie die Karte "Von selbst aktualisieren", mit der Zustimmung aus der Frage; Quellluecken einmal pro Woche (Vorgabe der Karte).
      schedule = {
        result <- service$schedule(state$runtime)$enable(unlist(step$times), "weekly", now_utc())
        if (!identical(result$status, "enabled")) .desktop_setup_fail_v1(if (is.character(result$code)) result$code else "desktop_setup_apply_failed")
        "enabled"
      },
      # Wie die Karte "Passwortschutz", aber ohne vorhandene Backups (13.11.2026): Der Backup-Ordner unter $XDG_STATE_HOME/portelyra
      # gehoert allen Homes des Benutzerkontos - bei einer Neuinstallation meist einem anderen Home. Mitgenommene Backups loescht
      # "Unverschluesselten Bestand entfernen" danach; so haette der Dialog die Backups eines anderen Bestands entfernt. Der Dialog
      # verschluesselt nur den Bestand, den er eben angelegt hat. Ein vorhandenes Backup zu uebernehmen gehoert ins Wiederherstellen (#559).
      protection = {
        password <- secrets$password
        if (!is.character(password) || length(password) != 1L || !nzchar(password)) .desktop_setup_fail_v1("desktop_setup_password_missing")
        result <- service$protection("enable", list(password = password, `repeat` = password, confirmed = TRUE,
                                                    backups_source = NULL, keyring = isTRUE(step$keyring)))
        if (!identical(result$status, "completed")) .desktop_setup_fail_v1(if (is.character(result$code)) result$code else "desktop_setup_apply_failed")
        state$recovery_key <- result$result$recovery_key
        if (isTRUE(result$result$keyring_failed)) "enabled_without_keyring" else "enabled"
      },
      # Update-Suche (#562): die Antwort in die Einstellungen der Installation (Programmordner), wie der Reiter „Programm“.
      updates = {
        invisible(desktop_installation_settings_write_v1(home, list(update_check = list(consent = isTRUE(step$consent), via = "setup"))))
        "set"
      },
      .desktop_setup_fail_v1("desktop_setup_apply_failed"))
  }
  results <- list()
  for (step in plan$steps) {
    outcome <- tryCatch(list(key = step$key, status = run_step(step)), error = function(error) {
      # Die Dienste der Karten melden ihren Code teils als Feld, teils als Meldung (stop(code)); beides wird gezeigt, sonst der allgemeine.
      code <- tryCatch(as.character(error$code), error = function(e) character())
      if (!(length(code) == 1L && nzchar(code))) code <- conditionMessage(error)
      list(key = step$key, status = "failed", code = if (length(code) == 1L && grepl("^[a-z][a-z0-9_]{2,80}$", code)) code else "desktop_setup_apply_failed")
    })
    results[[length(results) + 1L]] <- outcome
    if (identical(outcome$status, "failed")) break
  }
  structure(results, recovery_key = state$recovery_key)
}

# --- Seite ---------------------------------------------------------------------------------------------------------------------------

desktop_setup_ui_v1 <- function(css = "") shiny::fluidPage(
  shiny::tags$head(shiny::tags$meta(name = "viewport", content = "width=device-width, initial-scale=1"),
                   shiny::tags$meta(name = "referrer", content = "no-referrer"), shiny::tags$title(DESKTOP_SETUP_TEXT_V1$title),
                   shiny::tags$style(shiny::HTML(css))),
  # Bootstrap 3 setzt die Grundschrift auf 10 px; die Breite steht deshalb in px.
  shiny::div(class = "pl-setup", style = "max-width:720px;margin:40px auto;padding:0 16px;",
    shiny::h2(DESKTOP_SETUP_TEXT_V1$title),
    shiny::uiOutput("setup_body")))

.desktop_setup_panel_v1 <- function(title, copy, tone) if (exists("portelyra_status_panel", mode = "function")) portelyra_status_panel(title, copy, tone = tone) else
  shiny::div(shiny::strong(title), shiny::p(copy))

# Ein Schritt der Zusammenfassung als Zeile. Die Antworten des Nutzers stehen fett (Endabnahme 19.11.2026); ein Grund steht nur dabei,
# wenn er etwas erklaert („Später“, ohne Baustein) - „aus Ihrer Antwort“ sagt die Legende einmal oben.
.desktop_setup_step_lines_v1 <- function(step) {
  text <- DESKTOP_SETUP_TEXT_V1
  # Eine Zeile als zusammenhaengendes HTML: Text maskiert, Antworten fett, ohne Zwischenraum vor Satzzeichen.
  b <- function(x) structure(htmltools::htmlEscape(x), class = "pl_setup_bold")
  h <- function(...) shiny::HTML(paste0(vapply(list(...), function(part) if (inherits(part, "pl_setup_bold")) paste0("<strong>", unclass(part), "</strong>")
    else htmltools::htmlEscape(part), character(1L)), collapse = ""))
  reason <- function(code) switch(code, answer = NULL, later = "„Später“ – einschalten können Sie es in den Einstellungen",
    no_market_data = "ohne den Baustein Marktdaten", no_provider = "ohne Kursanbieter", present = "besteht schon", code)
  why <- function(code) {
    if (is.null(code) || identical(code, "answer")) return("")
    said <- if (code %in% names(text$reasons)) text$reasons[[code]] else reason(code)
    if (is.null(said)) "" else paste0(" – ", said)
  }
  switch(step$key,
    data_space = list(if (identical(step$action, "create")) "Datenraum auf diesem Rechner anlegen – hier liegen Ihre Daten, nur lokal."
                      else "Datenraum besteht schon – bleibt, wie er ist."),
    portfolio = list(if (identical(step$action, "create")) h("Portfolio ", b(sprintf("„%s“", step$display_name)), " in ", b(step$base_currency), " anlegen")
                     else h("Portfolio ", b(sprintf("„%s“", step$display_name)), sprintf(" (%s) besteht schon – wird genutzt", step$base_currency))),
    scope = {
      classes <- unlist(step$configuration$classes)
      labels <- text$questions$holdings$choices
      what <- if (length(classes) == length(setdiff(names(labels), "cash"))) "alle Assetklassen" else if (length(classes)) paste(labels[classes], collapse = ", ") else "keine Wertpapiere oder Krypto"
      modules <- lapply(names(text$modules), function(module) shiny::tags$li(h(paste0(text$modules[[module]], ": "),
        b(if (isTRUE(step$configuration$modules[[module]])) "an" else "aus"), paste0(why(step$reasons[[module]]), "."))))
      # Buchungsweg (#583): als eigene Zeile, weil „von Hand“ immer dabei ist; der Baustein Belege folgt der zweiten Antwort.
      ways <- if (isTRUE(step$configuration$modules$documents)) "von Hand und aus Belegen und Auszügen" else "nur von Hand"
      list(h("Erfasst wird: ", b(what), paste0(why(step$classes_reason), ".")),
           h("Gebucht wird: ", b(ways), paste0(why(step$reasons$documents), ".")),
           shiny::tagList("Bausteine dieses Portfolios:", shiny::tags$ul(modules)))
    },
    # Institute und Belegordner (#572); ohne den Baustein Belege keine Zeile, „Gebucht wird: nur von Hand“ sagt es schon.
    documents = if (identical(step$action, "set")) list(
        if (length(step$plugins)) h("Leser aktivieren für ", b(paste(vapply(step$plugins, function(item) as.character(item$label), character(1L)),
                                                                   collapse = ", ")), " – weitere in Daten → „Leser“.")
        else "Leser: keine gewählt – aktivieren lässt sich jeder in Daten → „Leser“.",
        if (is.character(step$intake_folder)) h("Belegordner: ", b(step$intake_folder), " – Portelyra liest ihn nur.")
        else "Belegordner: noch keiner – festlegen im Eingang.")
      else switch(as.character(step$reason), no_documents = list(),
        later = list("Leser und Belegordner: noch offen („Später“) – Leser in Daten → „Leser“, Belegordner im Eingang."),
        list("Leser und Belegordner: keine gewählt – Leser in Daten → „Leser“, Belegordner im Eingang.")),
    tax = if (!identical(step$action, "set")) list("Kein Steuerbereich – ohne den Baustein Steuerbericht.") else {
      years <- unlist(step$years); span <- sprintf("%d–%d", min(years), max(years))
      defaults <- lapply(step$type_defaults, function(row) shiny::tags$li(sprintf("%s → %s%s", text$asset_types[[row$asset_type]],
        text$classifications[[row$classification_code]], if (!identical(row$partial_exemption_rate_decimal, "0"))
          sprintf(", %s %% Teilfreistellung (Anleihe- und Mischfonds je Asset prüfen)", row$partial_exemption_rate_decimal) else "")))
      if (length(step$unclassified_classes)) defaults[[length(defaults) + 1L]] <- shiny::tags$li("Sonstiges: keine Vorgabe – je Asset in Daten → „Steuer“ einordnen")
      rate <- if (is.null(step$personal_income_tax_rate)) paste("Persönlicher Steuersatz: weiß ich nicht – Kapitalerträge rechnet Portelyra mit der",
                "Abgeltungsteuer, Krypto und sonstige Veräußerungen bleiben ohne Steuerzahl; nachtragen in Daten → „Steuer“ → „Steuerangaben je Jahr“.")
              else h("Persönlicher Steuersatz: ", b(sprintf("%s %%", sub(".", ",", step$personal_income_tax_rate, fixed = TRUE))), sprintf(" für %s.", span))
      church <- if (identical(step$church_tax_applicable, "applicable")) h("Kirchensteuer: ", b(sprintf("ja, %s %% (%s)", step$church_tax_rate,
                  text$questions$church$states[[step$church_state]])), sprintf(", für %s.", span))
                else if (identical(step$church_reason, "later")) "Kirchensteuer: vorerst nein („Später“) – änderbar in Daten → „Steuer“."
                else h("Kirchensteuer: ", b("nein"), sprintf(", für %s.", span))
      list("Steuerbereich einrichten, Regelmodul „Deutsches Referenzmodell v2“ für Ereignis, Jahr und Stichtag (ab 2016).",
           shiny::tagList("Einordnung je Asset-Typ (ab 2016):", shiny::tags$ul(defaults)), rate, church)
    },
    closing = list(if (identical(step$tax_mode, "disabled")) paste("Erster Abschluss ohne Steuermodul: Mit Ihrer Bestätigung legt Portelyra einen",
        "ersten Abschlusslauf an; „Alles aktualisieren“ erstellt den Abschluss, sobald Buchungen da sind. Ein Steuermodul lässt sich später",
        "einrichten: in Daten → „Steuer“ und einmal im Bereich „Abschluss“ das Steuermodul wählen – danach übernimmt „Alles aktualisieren“ es.")
      else paste("Erster Abschluss: Mit Ihrer Bestätigung gelten diese Vorgaben auch für den ersten Abschluss. Portelyra legt dazu einen ersten Abschlusslauf an;",
                 "„Alles aktualisieren“ erstellt den Abschluss, sobald Buchungen da sind.")),
    prices = list(if (identical(step$action, "activate")) h("Kursanbieter ", b("Yahoo Finance"), " aktivieren – Bedingungen zur Kenntnis genommen.")
                  else h("Kursanbieter: ", b("keiner"), paste0(why(step$reason), "."))),
    schedule = list(if (identical(step$action, "enable")) h("Zeitplan „Alles aktualisieren“: ", b(sprintf("täglich um %s Uhr",
                                                                  paste(unlist(step$times), collapse = " und "))), " – mit Ihrer Zustimmung.")
                    else h("Zeitplan: ", b("keiner"), paste0(why(step$reason), "."))),
    protection = list(if (identical(step$action, "enable")) h(b(paste0("Passwortschutz einrichten", if (isTRUE(step$keyring)) ", mit der Anmeldung entsperren" else "")),
                        ". Danach zeigt Portelyra einmal den Wiederherstellungsschlüssel; nach dem ersten Backup im verschlüsselten Ordner entfernt es den",
                        " unverschlüsselten Bestand.")
                      else if (identical(step$action, "keep")) "Passwortschutz ist schon eingerichtet – bleibt."
                      else h("Passwortschutz: ", b("keiner"), paste0(why(step$reason), "."))),
    updates = list(if (!identical(step$action, "set")) "Nach neuen Versionen suchen: noch offen („Später“) – die App „Daten“ fragt noch einmal."
                   else if (isTRUE(step$consent)) h("Nach neuen Versionen suchen: ", b("einmal am Tag automatisch"), " – mit Ihrer Zustimmung, bei GitHub.")
                   else h("Nach neuen Versionen suchen: ", b("nur auf Klick"), " in Daten → Einstellungen → „Programm“.")),
    list())
}

# Institute (#572): ein Haekchen je mitgeliefertem Leser, nebeneinander; Kennung und Name kommen aus dem Kern (questions_v1).
.desktop_setup_institutes_field_v1 <- function(id, words, item, given) {
  rows <- if (is.list(item$institutions)) item$institutions else list()
  choices <- stats::setNames(vapply(rows, function(row) as.character(row$plugin_id), character(1L)), vapply(rows, function(row) as.character(row$label), character(1L)))
  shiny::checkboxGroupInput(id, words$label, choices = choices, selected = if (is.list(given)) as.character(unlist(given)) else character(), inline = TRUE,
                            width = "100%")
}

desktop_setup_server_v1 <- function(project_root, home, on_done, runner = NULL, apply_runner = NULL, current = NULL,
                                    protection_available = function() nzchar(Sys.which("gocryptfs")), services = list()) function(input, output, session) {
  text <- DESKTOP_SETUP_TEXT_V1
  call <- function(command, payload = list()) desktop_setup_cli_v1(project_root, command, payload, runner)
  current_of <- if (is.function(current)) current else function() desktop_setup_current_v1(home)
  apply_of <- if (is.function(apply_runner)) apply_runner else function(plan, secrets) desktop_setup_apply_v1(project_root, home, plan, secrets, services = services)
  catalog <- call("questions")
  questions <- if (identical(catalog$status, "completed")) catalog$result$questions else list()
  keys <- vapply(questions, function(item) as.character(item$key), character(1L))
  later <- "later"
  draft <- call("draft-read", list(home = home))
  initial <- if (identical(draft$status, "completed") && is.list(draft$result$draft)) draft$result$draft else NULL
  position <- shiny::reactiveVal(if (is.null(initial)) "welcome" else initial$position)
  answers <- shiny::reactiveVal(if (is.null(initial)) structure(list(), names = character()) else initial$answers)
  feedback <- shiny::reactiveVal(NULL)
  noticed <- shiny::reactiveVal(isTRUE(tryCatch(desktop_first_use_notice_acknowledged_v1(home), error = function(error) FALSE)))
  shiny::observeEvent(input$setup_notice_continue, {
    if (!isTRUE(input$setup_notice_ack)) return(feedback(list(title = "Noch nicht bestätigt", copy = DESKTOP_FIRST_USE_NOTICE_V1$missing, tone = "warning")))
    written <- tryCatch(desktop_first_use_notice_acknowledge_v1(home), error = function(error) FALSE)
    feedback(if (isTRUE(written)) NULL else list(title = "Nicht gespeichert", copy = "Die Bestätigung ließ sich im Programmordner nicht speichern. Bitte erneut versuchen.", tone = "warning"))
    noticed(isTRUE(written))
  })
  plan <- shiny::reactiveVal(NULL)
  outcome <- shiny::reactiveVal(NULL)
  # Nur im Speicher dieser Sitzung, nie im Entwurf und nie in einer Ausgabe.
  secret <- shiny::reactiveVal(NULL)
  # Demo ansehen (#487 Teil 2, rc.413): ein eigenes Portelyra mit erfundenem Bestand, gestartet als eigener Prozess. Der Dialog zeigt nur
  # den Fortschritt; die eigene Einrichtung bleibt offen und unberuehrt. Die echten Wege sind im Test ersetzbar.
  # Kurse von Yahoo im Demo (rc.414):
  # der hervorgehobene Weg, mit denselben Hinweisen des Anbieters wie die Frage „Kurse“. Die Kenntnisnahme traegt der Knopf selbst - sein
  # Text sagt es direkt daneben; ohne Netz bleibt als zweiter Weg.
  demo_services <- utils::modifyList(list(
    start = function(prices = "none") desktop_demo_home_spawn_v1(project_root, home, Sys.getenv("PORTELYRA_BROWSER_NAME_INTERNAL", unset = ""), prices = prices),
    progress = function() desktop_demo_home_progress_v1(home)), if (is.list(services$demo)) services$demo else list())
  demo_notes <- local({
    item <- Filter(function(entry) identical(entry$key, "prices"), questions)
    if (length(item) && is.list(item[[1L]]$provider)) unlist(item[[1L]]$provider$notes) else character()
  })
  demo <- shiny::reactiveVal(NULL)
  demo_poll <- shiny::reactiveVal(0L)
  demo_start <- function(prices) {
    started <- tryCatch(demo_services$start(prices), error = function(error) list(status = "failed", code = "desktop_demo_home_build_failed"))
    demo(if (identical(started$status, "failed")) list(phase = "blocked", code = started$code, steps = list())
         else if (identical(started$status, "running")) list(phase = "started", steps = list(), already = TRUE)
         else list(phase = "waiting", steps = list(), prices = prices))
    demo_poll(demo_poll() + 1L)
  }
  shiny::observeEvent(input$setup_demo_yahoo, { feedback(NULL); demo_start("yahoo") })
  shiny::observeEvent(input$setup_demo_offline, { feedback(NULL); demo_start("none") })
  shiny::observe({
    demo_poll()
    current <- shiny::isolate(demo())
    if (!is.list(current) || isTRUE(current$phase %in% c("blocked", "started", "ended"))) return()
    shiny::invalidateLater(1500, session)
    following <- tryCatch(demo_services$progress(), error = function(error) current)
    if (is.list(following) && is.null(following$prices)) following$prices <- current$prices
    demo(following)
  })
  demo_panel <- function() {
    current <- demo(); if (!is.list(current)) return(NULL)
    labels <- c(install = "Programm einrichten", initialize = "Datenraum anlegen", setup = "Einrichtung übernehmen", catalog = "Konten und Assets",
                activities = "Buchungen", prices = "Kursangaben", cash = "Tagesgeld", refresh = "Alles aktualisieren", demo = "fertig")
    done <- vapply(current$steps, function(step) as.character(step$step), character(1L))
    progress <- if (length(done)) paste0(" Erledigt: ", paste(labels[intersect(names(labels), done)], collapse = ", "), ".") else ""
    set_up <- sum(vapply(current$steps, function(step) identical(step$step, "market_setup") && isTRUE(step$result %in% c("completed", "already_verified")), logical(1L)))
    market_copy <- switch(as.character(current$market %||% ""),
      active = "Die Kurse kommen von Yahoo Finance.",
      partial = paste("Für einen Teil der Assets kommen die Kurse von Yahoo Finance; die übrigen bewerten wie ohne Netz – mit den Kursen",
                      "der Buchungen oder erfundenen Kursangaben, keine Marktkurse. Die Ansichten nennen bei jedem Kurs die Herkunft.",
                      "„Mit aktuellen Kursen“ versucht es erneut."),
      unreachable = paste("Yahoo Finance war nicht erreichbar: Das Demo zeigt die Kurse der Buchungen und für vier Assets erfundene",
                          "Kursangaben, keine Marktkurse. „Mit aktuellen Kursen“ versucht es erneut."),
      failed = paste("Die Kurse von Yahoo ließen sich nicht einschalten: Das Demo zeigt die Kurse der Buchungen und für vier Assets",
                     "erfundene Kursangaben, keine Marktkurse."), "")
    switch(as.character(current$phase),
      blocked = .desktop_setup_panel_v1("Das Demo ist nicht gestartet", desktop_demo_home_reason_v1(current$code), "warning"),
      started = .desktop_setup_panel_v1("Das Demo läuft", paste(
        if (isTRUE(current$already)) "Es lief schon; ein zweites wird nicht gestartet." else "Es hat sich in einem eigenen Tab geöffnet.",
        market_copy, "Diese Einrichtung bleibt hier offen. Das Demo endet, wenn Sie Portelyra beenden."),
        if (isTRUE(current$market %in% c("unreachable", "failed"))) "neutral" else "positive"),
      market = .desktop_setup_panel_v1("Kurse von Yahoo werden eingerichtet", paste0(
        "Der Bestand ist aufgebaut. Portelyra richtet je Asset die Kurszuordnung ein und holt danach die Kurshistorie – einige Minuten.",
        if (set_up) sprintf(" Eingerichtet: %d Asset%s.", set_up, if (set_up == 1L) "" else "s") else ""), "neutral"),
      ended = .desktop_setup_panel_v1("Das Demo wurde beendet", "„Demo ansehen“ startet es wieder.", "neutral"),
      starting = .desktop_setup_panel_v1("Das Demo startet", paste0("Der Bestand ist aufgebaut; die Apps des Demos starten.", progress), "neutral"),
      .desktop_setup_panel_v1("Das Demo wird aufgebaut", paste0(
        if (isTRUE(demo_with_prices(current))) paste("Zuerst entsteht der Bestand ohne Netz – beim ersten Mal drei bis vier Minuten –, danach richtet",
                                                     "Portelyra die Kurse von Yahoo ein und holt die Kurshistorie.")
        else "Der Bestand entsteht ohne Netz; beim ersten Mal dauert das drei bis vier Minuten.",
        " Sie können hier weitermachen; das Demo öffnet sich von selbst.", progress), "neutral"))
  }
  # Mit Kursen von Yahoo? Gewaehlt beim Klick; nach einem Neuladen der Seite aus dem Stand erschlossen.
  demo_with_prices <- function(current) identical(current$prices, "yahoo") || identical(current$phase, "market") || !is.null(current$market)
  demo_busy <- function() { current <- demo(); is.list(current) && isTRUE(current$phase %in% c("waiting", "building", "market", "starting")) }
  # Fortschritt als Schrittanzeige (Endabnahme 19.11.2026): erledigt, laeuft, offen - ohne erfundene Prozentzahl fuer die Kursabrufe.
  demo_steps <- function() {
    current <- demo(); if (!is.list(current) || isTRUE(current$phase %in% c("blocked", "ended"))) return(NULL)
    phase <- as.character(current$phase); yahoo <- demo_with_prices(current)
    built <- phase %in% c("starting", "market", "started")
    priced <- !yahoo || phase == "started" || (phase == "starting" && !is.null(current$market))
    stages <- list(list(label = "Bestand aufbauen (ohne Netz)", state = if (built) "done" else "running"))
    if (yahoo) stages[[length(stages) + 1L]] <- list(label = "Kurse von Yahoo einrichten und Kurshistorie holen",
                                                     state = if (priced) "done" else if (built) "running" else "open")
    stages[[length(stages) + 1L]] <- list(label = "Demo öffnen", state = if (phase == "started") "done" else if (built && priced) "running" else "open")
    done <- sum(vapply(stages, function(stage) identical(stage$state, "done"), logical(1L)))
    word <- c(done = "erledigt", running = "läuft", open = "offen")
    shiny::div(class = "pl-steps", `aria-label` = sprintf("Schritt %d von %d", min(done + 1L, length(stages)), length(stages)),
      shiny::div(class = "pl-steps-bar", shiny::div(class = "pl-steps-fill", style = sprintf("width:%d%%;", as.integer(round(100 * done / length(stages)))))),
      shiny::tags$ol(lapply(stages, function(stage) shiny::tags$li(class = paste0("pl-step-", stage$state),
        shiny::span(class = "pl-step-label", stage$label), shiny::span(class = "pl-step-state", word[[stage$state]])))))
  }
  # Der Abschnitt auf der Startseite: Demo mit aktuellen Kursen (Yahoo) als erster Weg, ohne Netz als zweiter.
  demo_section <- function() shiny::div(class = "pl-field-group",
    shiny::h4(class = "pl-section-title", "Erst das Demo-Portfolio ansehen"),
    shiny::p(class = "pl-field-hint", paste("Ein eigenes Portelyra mit einem erfundenen Bestand auf echten Assets – zum Ausprobieren, getrennt von Ihren",
                                            "Daten. Mit Kursen von Yahoo Finance zeigt es echte Verläufe. Ohne Netz bewertet es mit den Kursen der Buchungen und",
                                            "für vier selten gekaufte Assets mit erfundenen Kursangaben – keine Marktkurse, sie können von den echten abweichen.")),
    if (length(demo_notes)) shiny::tags$ul(class = "pl-field-hint", lapply(demo_notes, shiny::tags$li)),
    demo_steps(),
    demo_panel(),
    # Waehrend des Aufbaus gesperrt (Endabnahme 19.11.2026); „Los geht's“ fuer die eigene Einrichtung bleibt bedienbar.
    shiny::div(class = "pl-editor-actions",
      # Das Attribut nur beim Sperren: Shiny 1.8.0 (Ubuntu 24.04) kennt den Parameter `disabled` noch nicht und reicht ihn als Attribut weiter.
      do.call(shiny::actionButton, c(list("setup_demo_yahoo", "Demo mit aktuellen Kursen ansehen", class = "btn-primary"), if (demo_busy()) list(disabled = TRUE))),
      do.call(shiny::actionButton, c(list("setup_demo_offline", "Demo ohne Netz ansehen", class = "btn-default"), if (demo_busy()) list(disabled = TRUE)))),
    if (demo_busy()) shiny::p(class = "pl-field-hint", "Solange das Demo aufgebaut wird, sind die beiden Knöpfe gesperrt."),
    shiny::p(class = "pl-field-hint", paste("Mit dem Klick auf „Demo mit aktuellen Kursen ansehen“ nehmen Sie die Hinweise und die Bedingungen des",
                                            "Anbieters zur Kenntnis. Portelyra ruft dann im Demo Kurse bei Yahoo Finance ab, nur lesend.")))

  # Wiederherstellen aus einem vorhandenen Backup (#559 Teil 2, rc.408): eigener Weg, danach nur Zeitplan und Passwortschutz.
  # Der Zwischenstand nach dem Uebernehmen (rc.410): ein Vermerk im Home (0600, nur Name, Programmstand, Bindung, Herkunft) und der
  # Entwurf an der Stelle "restore_followup". So macht der Dialog nach Neuladen oder Neustart bei Zeitplan und Passwortschutz weiter.
  restore_note <- file.path(home, "setup-restore.json")
  restore_resumed <- if (identical(shiny::isolate(position()), "restore_followup") && file.exists(restore_note) && !nzchar(Sys.readlink(restore_note)))
    tryCatch(jsonlite::fromJSON(restore_note, simplifyVector = FALSE), error = function(error) NULL) else NULL
  if (identical(shiny::isolate(position()), "restore_followup") && !is.list(restore_resumed))
    restore_resumed <- list(name = "–", product_version = "–", relocation = "", from_encrypted = FALSE)
  restore <- desktop_setup_restore_server_v1(input, session, .desktop_setup_restore_services_v1(project_root, home, if (is.list(services$restore)) services$restore else list()),
    position, feedback,
    remember = function(value) {
      old <- Sys.umask("0077"); on.exit(Sys.umask(old), add = TRUE)
      staged <- paste0(restore_note, ".", Sys.getpid())
      writeLines(as.character(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null")), staged, useBytes = TRUE)
      Sys.chmod(staged, "0600"); file.rename(staged, restore_note)
      call("draft-write", list(home = home, answers = structure(list(), names = character()), position = "restore_followup"))
    },
    resumed = restore_resumed,
    finish = function(results, key) {
      fingerprint <- digest::digest(as.character(jsonlite::toJSON(results, auto_unbox = TRUE)), algo = "sha256", serialize = FALSE)
      marked <- call("mark", list(home = home, status = "applied", plan_fingerprint = fingerprint, results = results))
      if (!identical(marked$status, "completed")) return(feedback(list(title = "Übernommen, aber nicht vermerkt", copy = desktop_setup_message_v1(marked$code), tone = "warning")))
      unlink(restore_note)
      secret(NULL)
      if (is.character(key) && length(key) == 1L && nzchar(key)) return(outcome(list(status = "key", key = key, results = results)))
      outcome(list(status = "applied", results = results)); on_done()
    },
    apply_followup = function(steps, password) apply_of(list(steps = steps), list(password = password)))

  # Schon uebernommen oder uebersprungen (etwa ein neuer Tab nach dem Wiederherstellungsschluessel): gleich weiter zum Start.
  already <- tryCatch(desktop_setup_status_v1(project_root, home, runner), error = function(error) NULL)
  if (is.list(already) && identical(already$status, "completed") && isTRUE(already$result$state %in% c("applied", "skipped"))) {
    outcome(list(status = already$result$state)); on_done()
  }

  # Die Reihenfolge der Fragen, die gestellt werden (Kurse nur mit Marktdaten, Zeitplan nur mit Kursanbieter).
  sequence_of <- function(values) {
    result <- call("applicable", list(answers = values))
    if (identical(result$status, "completed")) unlist(result$result$positions) else c("welcome", keys, "summary")
  }
  step_from <- function(at, values, by) {
    seq <- sequence_of(values)
    index <- match(at, seq)
    if (is.na(index)) index <- if (by > 0L) 1L else length(seq)
    seq[[max(1L, min(length(seq), index + by))]]
  }
  # Belegordner (#572): Hinweise in einer eigenen Ausgabe unter dem Feld. Eine Warnung ueber `feedback` zeichnete die ganze Frage neu, und die
  # eben gesetzten Haekchen der Institute waeren weg.
  folder_note <- shiny::reactiveVal(NULL)
  output$setup_intake_folder_note <- shiny::renderUI({ note <- folder_note(); if (is.list(note)) .desktop_setup_panel_v1(note$title, note$copy, note$tone) })
  choose_folder <- if (is.function(services$choose_folder)) services$choose_folder else function() data_statement_intake_choose_folder_v1()
  shiny::observeEvent(input$setup_intake_folder_pick, {
    picked <- tryCatch(choose_folder(), error = function(error) NULL)
    if (is.character(picked) && length(picked) == 1L && !is.na(picked) && nzchar(picked)) {
      shiny::updateTextInput(session, "setup_intake_folder", value = picked); folder_note(NULL)
    } else folder_note(list(title = "Kein Ordner gewählt", copy = "Den vollständigen Pfad können Sie auch eintippen.", tone = "neutral"))
  }, ignoreInit = TRUE)
  save <- function(next_position, values = answers()) {
    written <- call("draft-write", list(home = home, answers = values, position = next_position))
    if (!identical(written$status, "completed")) { feedback(list(title = "Nicht gespeichert", copy = desktop_setup_message_v1(written$code), tone = "warning")); return(FALSE) }
    answers(written$result$answers); position(next_position); feedback(NULL); folder_note(NULL); TRUE
  }
  refresh_plan <- function() {
    state <- tryCatch(current_of(), error = function(error) NULL)
    if (is.null(state)) { plan(NULL); feedback(list(title = "Stand nicht lesbar", copy = desktop_setup_message_v1("desktop_setup_state_invalid"), tone = "warning")); return() }
    result <- call("plan", list(answers = answers(), current = state))
    if (identical(result$status, "completed")) plan(c(result$result, list(current = state))) else {
      plan(NULL); feedback(list(title = "Keine Zusammenfassung", copy = desktop_setup_message_v1(result$code), tone = "warning"))
    }
  }
  shiny::observe({ if (identical(position(), "summary") && is.null(plan())) shiny::isolate(refresh_plan()) })
  warn <- function(title, copy) feedback(list(title = title, copy = copy, tone = "warning"))

  # Die Antwort der gezeigten Frage aus den Eingaben, samt ihren Zusatzangaben; NULL heisst: Hinweis gezeigt, nicht weiter.
  answers_with <- function(key) {
    item <- questions[[match(key, keys)]]
    value <- input[[paste0("setup_q_", key)]]
    values <- answers()
    values[[key]] <- if (identical(item$kind, "multi")) as.list(as.character(value)) else as.character(value)[1L]
    # Festgelegte Antworten (#583: „Von Hand“) gehoeren immer dazu, auch wenn der Browser das gesperrte Haekchen nicht mitschickt.
    if (length(item$fixed)) values[[key]] <- as.list(union(as.character(unlist(item$fixed)), as.character(unlist(values[[key]]))))
    if (identical(key, "holdings") && !length(values[[key]])) { warn("Bitte wählen", "Bitte mindestens eines wählen – oder „Später“."); return(NULL) }
    # Ohne Vorauswahl (#562): Weiter erst mit einer Antwort.
    if (identical(key, "updates") && !isTRUE(values$updates %in% c("daily", "manual"))) { warn("Bitte wählen", "Bitte eine der beiden Antworten wählen – oder „Später“."); return(NULL) }
    # Belegordner zu den Instituten (#572): freiwillig; dieselbe Regel wie „Als Belegordner festlegen“ im Eingang.
    if (identical(key, "institutes")) {
      folder <- trimws(as.character(input$setup_intake_folder %||% "")[1L])
      if (is.na(folder) || !nzchar(folder)) values$intake_folder <- NULL else {
        space <- tryCatch(runtime_data_space_path(desktop_product_runtime_load_v1(home)$context), error = function(error) NULL)
        checked <- if (is.character(space)) call("folder-check", list(folder = folder, data_space_path = space)) else list(status = "blocked")
        if (!identical(checked$status, "completed")) {
          folder_note(list(title = "Ordner prüfen", copy = desktop_setup_message_v1("desktop_setup_folder_invalid"), tone = "warning")); return(NULL) }
        values$intake_folder <- checked$result$folder
      }
    }
    if (identical(key, "prices")) {
      if (identical(values$prices, "yahoo") && !isTRUE(input$setup_prices_terms)) {
        warn("Bitte bestätigen", "Bitte die Hinweise und Bedingungen des Anbieters zur Kenntnis nehmen – oder „Keinen Anbieter“ wählen."); return(NULL) }
      values$prices_terms <- if (identical(values$prices, "yahoo")) TRUE else NULL
    }
    if (identical(key, "schedule")) {
      timed <- values$schedule %in% c("daily", "twice")
      if (timed && !isTRUE(input$setup_schedule_consent)) { warn("Zustimmung fehlt", "Der Zeitplan ruft Kurse ohne Ihr Zutun ab. Dafür das Häkchen „Zustimmung“ setzen."); return(NULL) }
      values$schedule_consent <- if (timed) TRUE else NULL
    }
    if (identical(key, "tax_rate")) {
      if (identical(values$tax_rate, "known")) {
        value <- trimws(as.character(input$setup_tax_rate_value)[1L])
        if (is.na(value) || !grepl("^[0-9]{1,3}([.,][0-9]{1,2})?$", value) || as.numeric(sub(",", ".", value, fixed = TRUE)) > 100) {
          warn("Satz prüfen", "Bitte den Satz in Prozent eingeben, etwa 30 oder 42,5 – oder „Weiß ich nicht“."); return(NULL) }
        values$tax_rate <- value
      } else values$tax_rate <- "unknown"
    }
    if (identical(key, "church")) {
      if (identical(values$church, "yes")) {
        state <- as.character(input$setup_church_state)[1L]
        if (is.na(state) || !state %in% names(text$questions$church$states)) { warn("Bundesland fehlt", "Bitte das Bundesland wählen."); return(NULL) }
        values$church_state <- state
      } else values$church_state <- NULL
    }
    if (identical(key, "protection")) {
      password <- input$setup_password; repeat_value <- input$setup_password_repeat
      for (id in c("setup_password", "setup_password_repeat")) shiny::updateTextInput(session, id, value = "")
      if (identical(values$protection, "yes")) {
        if (!isTRUE(protection_available())) { warn("Nicht verfügbar", text$questions$protection$missing_tool); return(NULL) }
        fresh <- is.character(password) && nzchar(password)
        if (fresh || is.null(secret())) {
          if (!is.character(password) || nchar(password) < 10L) { warn("Passwort zu kurz", desktop_protection_message_v1("desktop_protection_password_too_short")); return(NULL) }
          if (!identical(password, repeat_value)) { warn("Passwörter verschieden", "Die beiden Passwörter stimmen nicht überein."); return(NULL) }
          if (!isTRUE(input$setup_protection_understood)) { warn("Bitte bestätigen", "Bitte den Hinweis zum Verlust der Daten bestätigen."); return(NULL) }
          secret(password)
        }
        values$protection_keyring <- !identical(input$setup_protection_keyring, FALSE)
      } else { secret(NULL); values$protection_keyring <- NULL }
    }
    values
  }

  shiny::observeEvent(input$setup_start, save(step_from("welcome", answers(), 1L)))
  shiny::observeEvent(input$setup_back, { plan(NULL); save(step_from(position(), answers(), -1L)) })
  shiny::observeEvent(input$setup_next, {
    key <- position(); if (!key %in% keys) return()
    values <- answers_with(key); if (is.null(values)) return()
    plan(NULL); save(step_from(key, values, 1L), values)
  })
  shiny::observeEvent(input$setup_later, {
    key <- position(); if (!key %in% keys) return()
    values <- answers()
    if (identical(questions[[match(key, keys)]]$kind, "multi") || key %in% c("prices", "schedule", "protection", "tax_rate", "church", "updates")) values[[key]] <- later else values[[key]] <- NULL
    extras <- list(prices = "prices_terms", schedule = "schedule_consent", protection = "protection_keyring", church = "church_state",
                   institutes = "intake_folder")
    if (key %in% names(extras)) values[[extras[[key]]]] <- NULL
    if (identical(key, "protection")) secret(NULL)
    plan(NULL); save(step_from(key, values, 1L), values)
  })
  shiny::observeEvent(input$setup_edit, { plan(NULL); save(step_from("welcome", answers(), 1L)) })
  shiny::observeEvent(input$setup_password_again, { plan(NULL); save("protection") })
  shiny::observeEvent(input$setup_skip, {
    marked <- call("mark", list(home = home, status = "skipped"))
    if (!identical(marked$status, "completed")) return(feedback(list(title = "Nicht übersprungen", copy = desktop_setup_message_v1(marked$code), tone = "warning")))
    secret(NULL); outcome(list(status = "skipped")); on_done()
  })
  shiny::observeEvent(input$setup_apply, {
    shown <- plan(); if (is.null(shown)) return(refresh_plan())
    needs_password <- any(vapply(shown$steps, function(step) identical(step$key, "protection") && identical(step$action, "enable"), logical(1L)))
    if (needs_password && is.null(secret())) return(warn("Passwort fehlt", desktop_setup_message_v1("desktop_setup_password_missing")))
    state <- tryCatch(current_of(), error = function(error) NULL)
    confirmed <- call("confirm", list(answers = answers(), current = state, plan_fingerprint = shown$plan_fingerprint, confirmed = isTRUE(input$setup_confirm)))
    if (!identical(confirmed$status, "completed")) {
      if (identical(confirmed$code, "desktop_setup_plan_stale")) refresh_plan()
      return(warn("Noch nicht übernommen", desktop_setup_message_v1(confirmed$code)))
    }
    results <- apply_of(confirmed$result, list(password = secret()))
    key <- attr(results, "recovery_key")
    results <- lapply(results, function(item) item[intersect(names(item), c("key", "status", "code"))])
    failed <- Filter(function(item) identical(item$status, "failed"), results)
    if (length(failed)) {
      plan(NULL)
      return(warn("Einrichtung angehalten", sprintf("Schritt „%s“: %s (%s). Ihre Antworten bleiben als Entwurf; „Übernehmen“ setzt beim nächsten Versuch fort.",
        failed[[1L]]$key, desktop_setup_message_v1(failed[[1L]]$code), failed[[1L]]$code)))
    }
    marked <- call("mark", list(home = home, status = "applied", plan_fingerprint = confirmed$result$plan_fingerprint, results = results))
    if (!identical(marked$status, "completed")) return(warn("Eingerichtet, aber nicht vermerkt", desktop_setup_message_v1(marked$code)))
    secret(NULL)
    if (is.character(key) && length(key) == 1L && nzchar(key)) return(outcome(list(status = "key", key = key, results = results)))
    outcome(list(status = "applied", results = results)); on_done()
  })
  shiny::observeEvent(input$setup_key_continue, {
    done <- outcome(); if (!is.list(done) || !identical(done$status, "key")) return()
    if (!isTRUE(input$setup_key_noted)) return(warn("Bitte bestätigen", "Bitte bestätigen, dass der Wiederherstellungsschlüssel aufgeschrieben ist."))
    outcome(list(status = "applied", results = done$results)); on_done()
  })

  output$setup_body <- shiny::renderUI({
    note <- feedback(); done <- outcome(); at <- position()
    notice <- if (is.list(note)) .desktop_setup_panel_v1(note$title, note$copy, note$tone) else NULL
    if (!isTRUE(noticed())) return(shiny::tagList(
      shiny::h3(DESKTOP_FIRST_USE_NOTICE_V1$title),
      shiny::tags$ul(lapply(DESKTOP_FIRST_USE_NOTICE_V1$items, shiny::tags$li)),
      shiny::checkboxInput("setup_notice_ack", DESKTOP_FIRST_USE_NOTICE_V1$confirm, FALSE, width = "100%"),
      notice,
      shiny::div(class = "pl-editor-actions", shiny::actionButton("setup_notice_continue", DESKTOP_FIRST_USE_NOTICE_V1$continue, class = "btn-primary"))))
    if (is.list(done) && identical(done$status, "key")) return(shiny::tagList(
      shiny::h3("Ihr Wiederherstellungsschlüssel – nur jetzt sichtbar"),
      shiny::tags$pre(style = "font-size:1.15rem;user-select:all;", done$key),
      .desktop_setup_panel_v1("Bitte aufschreiben und sicher verwahren", paste(
        "Mit diesem Schlüssel setzen Sie ein neues Passwort, falls Sie es vergessen. Er öffnet alle Daten und Backups ohne Passwort und bleibt",
        "nach einer Passwortänderung gültig. Portelyra speichert ihn nicht. Sind Passwort und Schlüssel beide verloren, sind die Daten verloren."), "warning"),
      notice,
      shiny::checkboxInput("setup_key_noted", "Ich habe den Wiederherstellungsschlüssel aufgeschrieben.", FALSE),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("setup_key_continue", "Weiter: Portelyra starten", class = "btn-primary"))))
    if (is.list(done)) return(.desktop_setup_panel_v1(if (identical(done$status, "applied")) "Eingerichtet" else "Ohne Einrichtung",
      paste(if (identical(done$status, "applied")) "Portelyra startet mit diesem Umfang;" else "Portelyra startet; einrichten können Sie in der App „Daten“.",
            "die App „Daten“ öffnet sich gleich in einem neuen Tab. Diesen Tab können Sie schließen."), "positive"))
    if (identical(at, "welcome")) return(shiny::tagList(
      shiny::p("Ein paar Fragen, dann richtet Portelyra sich passend ein. Jede Frage dürfen Sie mit „Später“ beantworten; alles bleibt",
               "danach in den Einstellungen änderbar."),
      shiny::tags$ul(
        shiny::tags$li("Lokal: Ihre Daten bleiben auf diesem Rechner."),
        shiny::tags$li("Erst am Ende richtet Portelyra etwas ein – nach einer Zusammenfassung, die Sie bestätigen. Bis dahin merkt es sich",
                       "Ihre Antworten als Entwurf, auch über einen Neustart hinweg. Ein Passwort merkt es sich dabei nie."),
        shiny::tags$li("Keine Anlageberatung; die Steuerrechnung ist eine Modellrechnung ohne Gewähr.")),
      notice,
      shiny::div(class = "pl-editor-actions",
        shiny::actionButton("setup_start", "Los geht's", class = "btn-primary"),
        # Nur am Home ohne Datenbestand: Wiederherstellen geht nur beim ersten Start. Seit rc.410 immer angeboten, auch wenn der
        # Backup-Ordner von Portelyra leer ist - auf einem neuen Rechner nennt der Nutzer den Ordner selbst.
        if (!isTRUE(tryCatch(desktop_setup_data_space_present_v1(home), error = function(error) FALSE)))
          shiny::actionButton("setup_restore", "Aus einem vorhandenen Backup übernehmen", class = "btn-default"),
        shiny::actionButton("setup_skip", "Ohne Einrichtung starten", class = "btn-default")),
      # Demo ansehen (#487): ein eigenes Portelyra mit erfundenem Bestand; der eigene Bestand bleibt unberuehrt.
      demo_section()))
    if (at %in% c("restore", "restore_followup")) return(restore$body(at, notice))
    if (identical(at, "summary")) {
      shown <- plan()
      if (is.null(shown)) return(shiny::tagList(notice, shiny::div(class = "pl-editor-actions",
        shiny::actionButton("setup_edit", "Antworten ändern", class = "btn-default"),
        shiny::actionButton("setup_skip", "Ohne Einrichtung starten", class = "btn-default"))))
      lines <- unlist(lapply(shown$steps, .desktop_setup_step_lines_v1), recursive = FALSE)
      needs_password <- any(vapply(shown$steps, function(step) identical(step$key, "protection") && identical(step$action, "enable"), logical(1L)))
      return(shiny::tagList(
        shiny::h3("Das richtet Portelyra ein"),
        shiny::p(class = "pl-field-hint", "Fett: Ihre Antworten; alles andere ist die Vorgabe."),
        shiny::tags$ul(lapply(lines, shiny::tags$li)),
        shiny::p(class = "pl-field-hint", "Alles bleibt in den Einstellungen änderbar. Abschalten löscht nichts."),
        if (needs_password && is.null(secret())) shiny::tagList(
          .desktop_setup_panel_v1("Passwort neu eingeben", desktop_setup_message_v1("desktop_setup_password_missing"), "warning"),
          shiny::div(class = "pl-editor-actions", shiny::actionButton("setup_password_again", "Passwort eingeben", class = "btn-default"))),
        notice,
        shiny::checkboxInput("setup_confirm", "Ich habe die Zusammenfassung geprüft.", FALSE),
        shiny::div(class = "pl-editor-actions",
          shiny::actionButton("setup_apply", "Übernehmen und Portelyra starten", class = "btn-primary"),
          shiny::actionButton("setup_edit", "Antworten ändern", class = "btn-default"))))
    }
    seq <- sequence_of(answers()); asked <- setdiff(seq, c("welcome", "summary"))
    index <- match(at, keys); item <- questions[[index]]; words <- text$questions[[at]]; given <- answers()[[at]]
    if (is.character(words$copy)) words$copy <- sub("%ORIENTIERUNG%", desktop_tax_orientation_text_v1(project_root), words$copy, fixed = TRUE)
    if (is.character(words$bullets)) words$bullets <- sub("%ORIENTIERUNG%", desktop_tax_orientation_text_v1(project_root), words$bullets, fixed = TRUE)
    if (is.character(words$copy)) words$copy <- sub("%DATENSCHUTZ_UPDATES%", if (exists("DESKTOP_UPDATE_PRIVACY_V1")) DESKTOP_UPDATE_PRIVACY_V1 else "", words$copy, fixed = TRUE)
    id <- paste0("setup_q_", at)
    chosen <- if (is.character(given) && !identical(given, later)) given else item$default
    field <- if (identical(at, "institutes")) .desktop_setup_institutes_field_v1(id, words, item, given) else switch(item$kind,
      text = shiny::textInput(id, words$label, value = if (is.character(given)) given else item$default, width = "100%"),
      single = shiny::radioButtons(id, words$label, choices = stats::setNames(names(words$choices), unname(words$choices)), selected = chosen, width = "100%"),
      multi = shiny::checkboxGroupInput(id, words$label, choices = stats::setNames(names(words$choices), unname(words$choices)),
                                        selected = if (is.list(given)) unlist(given) else character(), width = "100%"),
      # Steuersatz: bekannt (mit Feld) oder "weiss ich nicht"; im Entwurf steht der Satz oder "unknown".
      rate = shiny::radioButtons(id, words$label, choices = stats::setNames(names(words$choices), unname(words$choices)),
                                 selected = if (is.character(given) && !given %in% c(later, "unknown")) "known" else "unknown", width = "100%"))
    # Kurse (Endabnahme 19.11.2026): Hinweise und Kenntnisnahme stehen eingerueckt direkt unter „Yahoo Finance“, nur wenn gewaehlt;
    # unter „Keinen Anbieter“ ein Satz zur Bewertung ohne Anbieter. Eine Radiogruppe, die Bindung von Shiny findet die Knoepfe am Namen.
    if (identical(at, "prices")) {
      option <- function(value) shiny::div(class = "radio", shiny::tags$label(
        shiny::tags$input(type = "radio", name = id, value = value, checked = if (identical(chosen, value)) NA else NULL),
        shiny::span(words$choices[[value]])))
      field <- shiny::div(id = id, class = "form-group shiny-input-radiogroup shiny-input-container", style = "width:100%;",
        shiny::tags$label(class = "control-label", id = paste0(id, "-label"), `for` = id, words$label),
        shiny::div(class = "shiny-options-group",
          option("yahoo"),
          shiny::div(class = "pl-choice-detail", shiny::conditionalPanel("input.setup_q_prices == 'yahoo'",
            shiny::tags$ul(class = "pl-field-hint", lapply(unlist(item$provider$notes), shiny::tags$li)),
            shiny::checkboxInput("setup_prices_terms", words$terms, isTRUE(answers()$prices_terms), width = "100%"))),
          option("none"),
          shiny::div(class = "pl-choice-detail", shiny::conditionalPanel("input.setup_q_prices == 'none'",
            shiny::p(class = "pl-field-hint", words$none_note)))))
    }
    # Buchungsweg (#583): eine Gruppe wie checkboxGroupInput, „Von Hand“ vorgewaehlt und gesperrt, je Antwort ein Hinweis darunter. Die
    # Bindung von Shiny findet die Haekchen am Namen und liest auch gesperrte; der Server nimmt „Von Hand“ ohnehin immer dazu.
    if (identical(at, "bookings")) {
      fixed <- as.character(unlist(item$fixed))
      ticked <- union(fixed, if (is.list(given)) as.character(unlist(given)) else character())
      option <- function(value) shiny::tagList(
        shiny::div(class = if (value %in% fixed) "checkbox disabled" else "checkbox", shiny::tags$label(
          shiny::tags$input(type = "checkbox", name = id, value = value, checked = if (value %in% ticked) NA else NULL,
                            disabled = if (value %in% fixed) NA else NULL),
          shiny::span(words$choices[[value]]))),
        shiny::div(class = "pl-choice-detail", shiny::p(class = "pl-field-hint", words$hints[[value]])))
      field <- shiny::div(id = id, class = "form-group shiny-input-checkboxgroup shiny-input-container", style = "width:100%;",
        shiny::tags$label(class = "control-label", id = paste0(id, "-label"), `for` = id, words$label),
        shiny::div(class = "shiny-options-group", lapply(names(words$choices), option)))
    }
    # Angezeigt, aber nicht waehlbar (Waehrungen, Schnittstelle): als Haekchen bei Mehrfachauswahl, sonst als Radioknopf.
    if (is.character(words$later_choices)) {
      kind <- if (identical(item$kind, "multi")) "checkbox" else "radio"
      field <- shiny::tagList(field, shiny::div(class = "pl-choice-later", lapply(unname(words$later_choices), function(label)
        shiny::div(class = paste(kind, "disabled"), shiny::tags$label(shiny::tags$input(type = kind, disabled = NA),
          shiny::span(class = "pl-muted", paste0(label, " – ", words$later_note)))))))
    }
    extra <- switch(at,
      institutes = shiny::div(class = "pl-field-group",
        shiny::textInput("setup_intake_folder", words$folder, value = answers()$intake_folder %||% "", width = "100%", placeholder = "/home/…/Belege"),
        shiny::div(class = "pl-editor-actions", shiny::actionButton("setup_intake_folder_pick", words$folder_pick, class = "btn-default")),
        shiny::p(class = "pl-field-hint", words$folder_hint),
        shiny::uiOutput("setup_intake_folder_note")),
      tax_rate = shiny::conditionalPanel("input.setup_q_tax_rate == 'known'",
        shiny::textInput("setup_tax_rate_value", words$value, value = if (is.character(given) && !given %in% c(later, "unknown"))
          sub(".", ",", given, fixed = TRUE) else "", width = "240px")),
      church = shiny::conditionalPanel("input.setup_q_church == 'yes'",
        shiny::selectInput("setup_church_state", words$state, choices = c(stats::setNames("", "Bitte wählen"),
          stats::setNames(names(words$states), unname(words$states))), selected = answers()$church_state %||% "", width = "320px")),
      schedule = shiny::conditionalPanel("input.setup_q_schedule != 'manual'",
        shiny::checkboxInput("setup_schedule_consent", words$consent, isTRUE(answers()$schedule_consent), width = "100%")),
      protection = if (!isTRUE(protection_available())) .desktop_setup_panel_v1("Nicht verfügbar", words$missing_tool, "neutral") else
        shiny::conditionalPanel("input.setup_q_protection == 'yes'",
          if (!is.null(secret())) shiny::p(class = "pl-field-hint", words$stored),
          shiny::passwordInput("setup_password", words$password, width = "100%"),
          shiny::passwordInput("setup_password_repeat", words$repeat_label, width = "100%"),
          shiny::checkboxInput("setup_protection_keyring", words$keyring, !identical(answers()$protection_keyring, FALSE), width = "100%"),
          shiny::p(class = "pl-field-hint", words$keyring_hint),
          shiny::checkboxInput("setup_protection_understood", words$understood, !is.null(secret()), width = "100%")),
      NULL)
    shiny::tagList(
      shiny::p(class = "pl-field-hint", sprintf("Frage %d von %d", match(at, asked, nomatch = index), length(asked))),
      shiny::h3(words$title), shiny::p(words$copy), if (is.character(words$bullets)) shiny::tags$ul(class = "pl-field-hint", lapply(words$bullets, shiny::tags$li)),
      field, extra, notice,
      shiny::div(class = "pl-editor-actions",
        shiny::actionButton("setup_next", "Weiter", class = "btn-primary"),
        shiny::actionButton("setup_later", "Später", class = "btn-default"),
        shiny::actionButton("setup_back", "Zurück", class = "btn-default")))
  })
}

# Fuer das Startskript: Erscheint der Dialog (erster Start oder Entwurf), die Seite auf `port` zeigen, bis uebernommen oder
# uebersprungen ist. Sonst sofort zurueck. Mit `token` (#563) oeffnet die Seite nur mit genau diesem Start-Token in der Adresse.
desktop_setup_blocking_v1 <- function(project_root, home, port, open_browser = NULL, css = "", token = NULL, services = list()) {
  status <- desktop_setup_status_v1(project_root, home)
  if (!identical(status$status, "completed") || !isTRUE(status$result$needed)) return(invisible(status))
  app <- shiny::shinyApp(desktop_setup_ui_v1(css), desktop_page_guard_v1(
    desktop_setup_server_v1(project_root, home, function() later::later(function() shiny::stopApp(TRUE), 1.5), services = services), token))
  if (is.function(open_browser)) later::later(function() open_browser(desktop_page_url_v1(port, token)), 0.5)
  shiny::runApp(app, host = "127.0.0.1", port = port, launch.browser = FALSE, quiet = TRUE)
  invisible(desktop_setup_status_v1(project_root, home))
}
