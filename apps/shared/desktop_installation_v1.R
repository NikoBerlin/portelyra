# Einstellungen der Installation (#586, #562; 0.3.3). Sie gelten je Installation, nicht je Portfolio, und liegen deshalb im Programmordner
# (<home>/installation-settings.json, 0600), nicht im Datenbestand und auch nicht im verschluesselten: Der Start liest sie, bevor entsperrt
# ist (schon die Entsperrseite oeffnet im gewaehlten Browser), und Backup oder Wiederherstellen des Bestands nehmen sie nicht mit.
# Geschrieben wird ueber eine temporaere Datei und Umbenennen; Felder, die diese Version nicht kennt (aus einer spaeteren), bleiben stehen.
# Nur Startskript und Data-App laden diese Datei; Cockpit, Steuer und Analyse schreiben nie (contracts/desktop-installation/v1).

DESKTOP_INSTALLATION_SETTINGS_FILE_V1 <- "installation-settings.json"
DESKTOP_INSTALLATION_VERSION_RE_V1 <- "^[0-9]+[.][0-9]+[.][0-9]+(-rc[.][0-9]+)?$"
# Wo die Zustimmung zur Update-Suche gegeben oder abgelehnt wurde (#562): Einrichtungsdialog, einmalige Karte in Data, Reiter „Programm“.
DESKTOP_UPDATE_DECIDED_VIA_V1 <- c("setup", "card", "settings")
# Derselbe Hinweis im Einrichtungsdialog, in der Karte und im Reiter „Programm“ (Festlegung 25.11.2026: Adresse, Haeufigkeit, was GitHub sieht).
DESKTOP_UPDATE_PRIVACY_V1 <- paste(
  "Portelyra fragt dafür höchstens einmal am Tag die Liste der Versionen bei GitHub ab (api.github.com).",
  "GitHub erfährt dabei Ihre IP-Adresse und den Zeitpunkt, aber nichts aus Ihrem Bestand und keine Kennung.",
  "Eingespielt wird ein Update erst nach Ihrer Bestätigung. Ohne Zustimmung sucht Portelyra nur, wenn Sie in den Einstellungen",
  "unter „Programm“ auf „Nach Updates suchen“ klicken.")

# Bekannte Browser (#586): Kennung, Name, Programme im Suchpfad oder unter /snap/bin, Kennung bei Flatpak. Portelyra installiert keinen
# Browser; angeboten wird nur, was auf dem Rechner gefunden wird. Geprueft wird mit Firefox.
DESKTOP_BROWSERS_V1 <- list(
  firefox = list(label = "Firefox", commands = "firefox", flatpak = "org.mozilla.firefox"),
  chromium = list(label = "Chromium", commands = c("chromium", "chromium-browser"), flatpak = "org.chromium.Chromium"),
  `google-chrome` = list(label = "Google Chrome", commands = c("google-chrome-stable", "google-chrome"), flatpak = "com.google.Chrome"),
  brave = list(label = "Brave", commands = c("brave-browser", "brave"), flatpak = "com.brave.Browser"),
  `microsoft-edge` = list(label = "Microsoft Edge", commands = c("microsoft-edge-stable", "microsoft-edge"), flatpak = "com.microsoft.Edge"),
  vivaldi = list(label = "Vivaldi", commands = c("vivaldi-stable", "vivaldi"), flatpak = "com.vivaldi.Vivaldi"),
  opera = list(label = "Opera", commands = "opera", flatpak = "com.opera.Opera"),
  librewolf = list(label = "LibreWolf", commands = "librewolf", flatpak = "io.gitlab.librewolf-community"),
  epiphany = list(label = "GNOME Web", commands = c("epiphany", "epiphany-browser"), flatpak = "org.gnome.Epiphany"))
DESKTOP_BROWSER_NAMES_V1 <- c("default", names(DESKTOP_BROWSERS_V1))

desktop_installation_settings_path_v1 <- function(home) file.path(home, DESKTOP_INSTALLATION_SETTINGS_FILE_V1)
# Sys.readlink: "" ohne Link, NA wenn die Datei fehlt.
.desktop_installation_symlink_v1 <- function(path) { link <- Sys.readlink(path); isTRUE(!is.na(link) && nzchar(link)) }

# Ergebnis: status ("absent", "available", "unreadable", "rejected" bei einem symbolischen Link, "newer" bei einer spaeteren
# Vertragsfassung), settings (gepruefte Werte, sonst die Vorgaben) und raw (die gelesenen Felder, nur bei "available").
desktop_installation_settings_read_v1 <- function(home) {
  defaults <- list(browser = "default", whats_new_seen_version = NULL, update_consent = NULL, update_decided_via = NULL)
  path <- desktop_installation_settings_path_v1(home)
  if (.desktop_installation_symlink_v1(path)) return(list(status = "rejected", settings = defaults, raw = list()))
  if (!file.exists(path)) return(list(status = "absent", settings = defaults, raw = list()))
  raw <- tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(raw) || (length(raw) && (is.null(names(raw)) || any(!nzchar(names(raw)))))) {
    return(list(status = "unreadable", settings = defaults, raw = list()))
  }
  if (!is.null(raw$contract_version) && !identical(suppressWarnings(as.integer(raw$contract_version)), 1L)) {
    return(list(status = "newer", settings = defaults, raw = list()))
  }
  settings <- defaults
  if (is.character(raw$browser) && length(raw$browser) == 1L && raw$browser %in% DESKTOP_BROWSER_NAMES_V1) settings$browser <- raw$browser
  if (is.character(raw$whats_new_seen_version) && length(raw$whats_new_seen_version) == 1L &&
      grepl(DESKTOP_INSTALLATION_VERSION_RE_V1, raw$whats_new_seen_version)) settings$whats_new_seen_version <- raw$whats_new_seen_version
  # Update-Suche (#562, Paket 3): Zustimmung zur taeglichen Suche; fehlt sie, ist noch nicht gefragt (Dialog oder Karte in Data).
  check <- raw$update_check
  if (is.list(check) && is.logical(check$consent) && length(check$consent) == 1L && !is.na(check$consent)) {
    settings$update_consent <- check$consent
    if (is.character(check$via) && length(check$via) == 1L && check$via %in% DESKTOP_UPDATE_DECIDED_VIA_V1) settings$update_decided_via <- check$via
  }
  list(status = "available", settings = settings, raw = raw)
}

# Aendert nur die genannten Felder. Eine unlesbare Datei wird neu angelegt; ein symbolischer Link oder eine spaetere Vertragsfassung nie
# ueberschrieben. Fehler als Bedingung mit Code (desktop_installation_settings_*).
desktop_installation_settings_write_v1 <- function(home, changes, now = Sys.time()) {
  fail <- function(code) stop(structure(class = c("desktop_installation_error_v1", "error", "condition"), list(message = code, call = NULL, code = code)))
  allowed <- c("browser", "whats_new_seen_version", "update_check")
  if (!is.list(changes) || !length(changes) || is.null(names(changes)) || !all(names(changes) %in% allowed)) fail("desktop_installation_settings_invalid")
  if (!is.null(changes$update_check)) {
    check <- changes$update_check
    if (!is.list(check) || !is.logical(check$consent) || length(check$consent) != 1L || is.na(check$consent) ||
        !(is.character(check$via) && length(check$via) == 1L && check$via %in% DESKTOP_UPDATE_DECIDED_VIA_V1)) fail("desktop_installation_settings_invalid")
    changes$update_check <- list(consent = check$consent, via = check$via, decided_at_utc = format(now, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  }
  if (!is.null(changes$browser) && !(is.character(changes$browser) && length(changes$browser) == 1L && changes$browser %in% DESKTOP_BROWSER_NAMES_V1)) {
    fail("desktop_installation_settings_invalid")
  }
  if (!is.null(changes$whats_new_seen_version) && !(is.character(changes$whats_new_seen_version) && length(changes$whats_new_seen_version) == 1L &&
                                                     grepl(DESKTOP_INSTALLATION_VERSION_RE_V1, changes$whats_new_seen_version))) {
    fail("desktop_installation_settings_invalid")
  }
  if (!dir.exists(home)) fail("desktop_installation_settings_home_missing")
  current <- desktop_installation_settings_read_v1(home)
  if (identical(current$status, "rejected")) fail("desktop_installation_settings_rejected")
  if (identical(current$status, "newer")) fail("desktop_installation_settings_newer")
  value <- if (identical(current$status, "available")) current$raw else list()
  for (key in names(changes)) value[[key]] <- changes[[key]]
  value$contract_version <- 1L
  value$updated_at_utc <- format(now, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  path <- desktop_installation_settings_path_v1(home)
  temporary <- paste0(path, ".tmp-", Sys.getpid())
  old_umask <- Sys.umask("0077")
  on.exit(Sys.umask(old_umask), add = TRUE)
  written <- tryCatch({
    writeLines(enc2utf8(as.character(jsonlite::toJSON(value, auto_unbox = TRUE, pretty = TRUE, null = "null"))), temporary, useBytes = TRUE)
    Sys.chmod(temporary, mode = "0600")
    file.rename(temporary, path)
  }, error = function(error) FALSE)
  if (!isTRUE(written)) { unlink(temporary); fail("desktop_installation_settings_write_failed") }
  desktop_installation_settings_read_v1(home)
}

.desktop_installation_data_home_v1 <- function() {
  data_home <- Sys.getenv("XDG_DATA_HOME", unset = "")
  if (nzchar(data_home)) data_home else file.path(path.expand("~"), ".local", "share")
}

# Installierte Browser: zuerst im Suchpfad, dann unter /snap/bin (fehlt im Suchpfad mancher Starts), dann als Flatpak (System und Benutzer).
# Ergebnis je gefundener Kennung: id, label, command (Pfad), kind ("system", "snap", "flatpak").
desktop_browsers_detect_v1 <- function(which = function(name) unname(Sys.which(name)), exists = file.exists, snap_bin = "/snap/bin",
                                       flatpak_bins = c("/var/lib/flatpak/exports/bin", file.path(.desktop_installation_data_home_v1(), "flatpak", "exports", "bin"))) {
  found <- list()
  for (id in names(DESKTOP_BROWSERS_V1)) {
    entry <- DESKTOP_BROWSERS_V1[[id]]
    path <- ""
    kind <- "system"
    for (command in entry$commands) {
      candidate <- which(command)
      if (length(candidate) == 1L && !is.na(candidate) && nzchar(candidate)) { path <- candidate; break }
    }
    if (!nzchar(path)) for (command in entry$commands) {
      candidate <- file.path(snap_bin, command)
      if (isTRUE(exists(candidate))) { path <- candidate; break }
    }
    if (!nzchar(path)) for (directory in flatpak_bins) {
      candidate <- file.path(directory, entry$flatpak)
      if (isTRUE(exists(candidate))) { path <- candidate; kind <- "flatpak"; break }
    }
    if (!nzchar(path)) next
    if (startsWith(path, paste0(snap_bin, "/"))) kind <- "snap"
    found[[id]] <- list(id = id, label = entry$label, command = path, kind = kind)
  }
  found
}

desktop_browser_label_v1 <- function(browser) {
  if (!is.list(browser)) return("Standardbrowser des Systems")
  suffix <- switch(if (is.character(browser$kind)) browser$kind else "system", snap = " (Snap)", flatpak = " (Flatpak)", "")
  paste0(browser$label, suffix)
}

# Welcher Browser oeffnet (#586). `requested` kommt von --browser und geht vor: "default" oder eine Kennung, die gefunden werden muss
# (sonst desktop_product_dependency_missing, wie bisher bei --browser firefox). Ohne --browser gilt die Wahl in den Einstellungen; ist der
# gewaehlte Browser nicht mehr da, oeffnet der Standardbrowser, und `fallback` nennt die Wahl (kein Abbruch). Ergebnis: name ("default"
# oder Kennung), command (Pfad; NULL fuer den Standardbrowser des Systems), source ("command_line", "setting", "default"), fallback.
desktop_browser_resolve_v1 <- function(home, requested = NULL, detect = desktop_browsers_detect_v1) {
  standard <- function(source, fallback = NULL) list(name = "default", command = NULL, source = source, fallback = fallback)
  # Wie .desktop_product_abort_v1 (spotcore): safe_main des Startskripts gibt den Code aus dem Fehlerkatalog weiter.
  abort <- function(code) stop(structure(class = c("spot_desktop_product_error_v1", "desktop_installation_error_v1", "error", "condition"),
                                         list(message = code, call = NULL, code = code)))
  if (!is.null(requested)) {
    if (!is.character(requested) || length(requested) != 1L || !requested %in% DESKTOP_BROWSER_NAMES_V1) abort("desktop_product_cli_input_invalid")
    if (identical(requested, "default")) return(standard("command_line"))
    found <- detect()[[requested]]
    if (is.null(found)) abort("desktop_product_dependency_missing")
    return(list(name = requested, command = found$command, source = "command_line", fallback = NULL))
  }
  chosen <- tryCatch(desktop_installation_settings_read_v1(home)$settings$browser, error = function(error) "default")
  if (!is.character(chosen) || identical(chosen, "default")) return(standard("default"))
  found <- tryCatch(detect()[[chosen]], error = function(error) NULL)
  if (is.null(found)) return(standard("setting", chosen))
  list(name = chosen, command = found$command, source = "setting", fallback = NULL)
}

# Oeffnet `url` im aufgeloesten Browser: der Standardbrowser wie bisher ueber die R-Option `browser` (xdg-open), ein gewaehlter direkt,
# abgekoppelt und ohne Ausgabe. system2 setzt das Programm selbst in Anfuehrungszeichen, die Adresse ist ein einziges Argument.
desktop_browser_open_v1 <- function(url, browser) {
  if (!is.list(browser) || is.null(browser$command)) return(invisible(utils::browseURL(url, browser = getOption("browser"))))
  invisible(system2(browser$command, shQuote(url), stdout = FALSE, stderr = FALSE, wait = FALSE))
}

# Wie .desktop_product_entry_quote_v1 (spotcore): Exec nach der Desktop-Entry-Spezifikation. Ein Test vergleicht beide.
.desktop_installation_entry_quote_v1 <- function(value) paste0('"', gsub("%", "%%", gsub('(["`$\\\\])', "\\\\\\1", value), fixed = TRUE), '"')

# Starter von vor 0.3.3 tragen die Browserwahl als `--browser <name>` in der Zeile Exec (#586). Die Kommandozeile ginge jeder Wahl im
# Reiter „Programm“ vor; die Wahl gehoert jetzt in die Einstellungen der Installation. Beim Start des neuen Stands wandert sie dorthin, wenn
# dort noch nichts gewaehlt ist, und `--browser <name>` verschwindet aus der ersten Zeile Exec. Angefasst wird nur portelyra.desktop, und nur,
# wenn sein Start dieses Programm aufruft (wie bei der Bildmarke, #584); sonst nichts. Ergebnis: "moved" (Wahl uebernommen), "removed"
# (Wahl stand schon in den Einstellungen), "current", "other_home", "no_entry" oder "failed".
desktop_installation_entry_browser_migrate_v1 <- function(source_root, home, data_home = .desktop_installation_data_home_v1()) {
  entry <- file.path(data_home, "applications", "portelyra.desktop")
  if (!file.exists(entry) || .desktop_installation_symlink_v1(entry)) return("no_entry")
  lines <- tryCatch(readLines(entry, warn = FALSE, encoding = "UTF-8"), error = function(error) character())
  exec_at <- grep("^Exec=", lines)
  script <- .desktop_installation_entry_quote_v1(file.path(source_root, "scripts", "portelyra_desktop.R"))
  if (!length(exec_at) || !grepl(paste0(script, " start"), lines[[exec_at[[1L]]]], fixed = TRUE)) return("other_home")
  exec <- lines[[exec_at[[1L]]]]
  pattern <- " --browser ([a-z][a-z-]*)( |$)"
  if (!grepl(pattern, exec)) return("current")
  name <- sub(paste0("^.*", pattern, ".*$"), "\\1", exec)
  current <- desktop_installation_settings_read_v1(home)
  result <- "removed"
  if (name %in% names(DESKTOP_BROWSERS_V1) && current$status %in% c("absent", "available") && is.null(current$raw$browser)) {
    stored <- tryCatch(desktop_installation_settings_write_v1(home, list(browser = name)), error = function(error) NULL)
    if (is.null(stored)) return("failed")
    result <- "moved"
  }
  lines[[exec_at[[1L]]]] <- sub(pattern, "\\2", exec)
  temporary <- paste0(entry, ".tmp-", Sys.getpid())
  written <- tryCatch({ writeLines(enc2utf8(lines), temporary, useBytes = TRUE); TRUE }, error = function(error) FALSE)
  if (!written) { unlink(temporary); return("failed") }
  Sys.chmod(temporary, mode = "0644")
  if (!file.rename(temporary, entry)) { unlink(temporary); return("failed") }
  result
}

# Kern der Update-Suche (scripts/desktop_update.py, #562 Paket 3): JSON ueber stdin, eine Zeile zurueck. Nur Data (Klick auf „Nach Updates
# suchen“) und das Startskript (taegliche Suche mit Zustimmung) rufen ihn; Cockpit, Steuer und Analyse lesen nur update-status.json.
desktop_update_cli_v1 <- function(project_root, command, payload = list(), runner = NULL, timeout = 40) {
  if (is.function(runner)) return(runner(command, payload))
  python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "desktop_update.py")
  if (!nzchar(python) || !file.exists(cli)) return(list(status = "blocked", code = "desktop_update_state_invalid"))
  json <- as.character(jsonlite::toJSON(if (length(payload)) payload else structure(list(), names = character()), auto_unbox = TRUE,
                                        null = "null", digits = NA))
  output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command), stdout = TRUE, stderr = FALSE, input = json,
                                     timeout = timeout))
  parsed <- tryCatch(jsonlite::fromJSON(utils::tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(parsed) || !is.character(parsed$status)) list(status = "blocked", code = "desktop_update_state_invalid") else parsed
}

# Ob die taegliche Suche faellig ist, ohne Netz und ohne Python: nur mit Zustimmung und wenn die letzte Abfrage (gleich welche) mehr als
# einen Tag her ist. Der Kern prueft beim Abfragen noch einmal selbst (due_v1).
desktop_update_due_v1 <- function(home, now = Sys.time()) {
  consent <- tryCatch(desktop_installation_settings_read_v1(home)$settings$update_consent, error = function(error) NULL)
  if (!isTRUE(consent)) return(list(due = FALSE, reason = "consent_missing"))
  path <- file.path(home, "update-status.json")
  if (!file.exists(path)) return(list(due = TRUE, reason = "due"))
  status <- tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(error) NULL)
  last <- if (is.list(status) && is.character(status$checked_at_utc) && length(status$checked_at_utc) == 1L) {
    as.POSIXct(status$checked_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  } else as.POSIXct(NA)
  if (!is.na(last) && last <= now && as.numeric(difftime(now, last, units = "secs")) < 86400) return(list(due = FALSE, reason = "not_due"))
  list(due = TRUE, reason = "due")
}

# Update aus der App (#562 Paket 4) ------------------------------------------------------------------------------------------------------
.desktop_update_state_dir_v1 <- function() {
  state_root <- Sys.getenv("XDG_STATE_HOME", unset = "")
  if (!nzchar(state_root)) state_root <- file.path(path.expand("~"), ".local", "state")
  file.path(state_root, "portelyra")
}

# Ein heruntergeladenes Archiv pruefen wie Schritt 1 von `update` (Befehl update-check des installierten Programms): Signatur gegen die
# installierte Vertrauensliste, Versionen. Nichts wird eingespielt. Zurueck kommt die letzte JSON-Zeile.
desktop_update_installed_check_v1 <- function(project_root, home, archive, runner = NULL, timeout = 300) {
  if (is.function(runner)) return(runner(archive))
  script <- file.path(project_root, "scripts", "portelyra_desktop.R")
  output <- suppressWarnings(system2(file.path(R.home("bin"), "Rscript"), c("--vanilla", shQuote(script), "update-check", "--archive", shQuote(archive)),
                                     stdout = TRUE, stderr = FALSE, timeout = timeout, env = paste0("PORTELYRA_DESKTOP_HOME=", shQuote(home))))
  parsed <- tryCatch(jsonlite::fromJSON(utils::tail(output[nzchar(trimws(output))], 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (is.list(parsed) && is.character(parsed$status)) parsed else list(status = "blocked", code = "desktop_product_boundary_failed")
}

# Das Update starten: das installierte `update` mit --page, abgekoppelt (setsid) und in einer eigenen Einheit der Sitzung
# (portelyra-update-…, #588), Ausgabe nach $XDG_STATE_HOME/portelyra/update-<version>.log. Es beendet Portelyra - auch die App, die es
# startet -, sichert, spielt ein und startet neu; den Fortschritt zeigt seine eigene Seite. `unit`: Ergebnis von .desktop_product_app_unit_v1
# (spotcore) mit kind "update", ohne Einheit wie bisher nur abgekoppelt. Die geerbte Zugangsdatei der laufenden Sitzung gilt dort nicht.
desktop_update_spawn_v1 <- function(project_root, home, archive, version, port, unit = NULL, runner = NULL) {
  log_dir <- .desktop_update_state_dir_v1()
  old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
  if (!dir.exists(log_dir)) dir.create(log_dir, recursive = TRUE, mode = "0700")
  log <- file.path(log_dir, paste0("update-", version, ".log"))
  script <- file.path(project_root, "scripts", "portelyra_desktop.R")
  prefix <- if (is.list(unit) && is.character(unit$prefix)) unit$prefix else character()
  command <- c("-f", prefix, "env", "-u", "PORTELYRA_ACCESS_FILE_INTERNAL", paste0("PORTELYRA_DESKTOP_HOME=", home),
               file.path(R.home("bin"), "Rscript"), script, "update", "--archive", archive, "--confirm", "UPGRADE_LOCAL_RUNTIME", "--page",
               "--port", as.character(as.integer(port)))
  setsid <- unname(Sys.which("setsid"))
  if (is.function(runner)) return(runner(setsid, command, log))
  if (!nzchar(setsid)) return(list(status = "blocked", code = "setsid_missing"))
  started <- tryCatch(system2(setsid, shQuote(command), stdout = log, stderr = log, stdin = "/dev/null", wait = FALSE), error = function(error) NA)
  if (!identical(as.integer(started), 0L)) return(list(status = "blocked", code = "spawn_failed"))
  list(status = "started", log = log, unit = if (is.list(unit)) unit$unit else NULL)
}
