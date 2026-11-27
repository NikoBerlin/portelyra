# Programm (#562, 0.3.3): Version des laufenden Programms, „Neu in dieser Version“ aus dem mitgelieferten CHANGELOG.md und die Zeile im
# Block links aller vier Apps. Nur lesend: Gelesen werden VERSION und CHANGELOG.md des Programms, das die App ausfuehrt (project_root);
# kein Netz, kein Datenbestand. Das Einzige, was geschrieben wird - vermerken, dass „Neu in dieser Version“ einmal gezeigt wurde, und die
# Browserwahl -, liegt in der Data-App (apps/data/data_program_v1.R) und in apps/shared/desktop_installation_v1.R.

DESKTOP_PROGRAM_VERSION_RE_V1 <- "^[0-9]+[.][0-9]+[.][0-9]+(-rc[.][0-9]+)?$"

# Version aus VERSION des Programms; NA, wenn sie fehlt oder nicht die Form x.y.z bzw. x.y.z-rc.N hat.
desktop_program_version_v1 <- function(project_root) {
  path <- file.path(project_root, "VERSION")
  value <- if (file.exists(path)) tryCatch(readLines(path, n = 1L, warn = FALSE, encoding = "UTF-8"), error = function(error) character()) else character()
  value <- if (length(value)) trimws(value[[1L]]) else ""
  if (grepl(DESKTOP_PROGRAM_VERSION_RE_V1, value)) value else NA_character_
}

# Abschnitt "## <Version>" des CHANGELOG (das erste Wort der Ueberschrift zaehlt). Eine Vorabversion x.y.z-rc.N zeigt den Abschnitt
# ihrer Version x.y.z, solange es ihn nicht gibt "## Unreleased" - das ist, was sie gegenueber der letzten Version mitbringt.
# Ergebnis: status "available" mit blocks, sonst "version_unknown", "changelog_missing", "section_missing" oder "section_empty".
desktop_program_changelog_v1 <- function(project_root, version) {
  if (!is.character(version) || length(version) != 1L || is.na(version) || !grepl(DESKTOP_PROGRAM_VERSION_RE_V1, version)) {
    return(list(status = "version_unknown"))
  }
  path <- file.path(project_root, "CHANGELOG.md")
  lines <- if (file.exists(path)) tryCatch(readLines(path, warn = FALSE, encoding = "UTF-8"), error = function(error) NULL) else NULL
  if (is.null(lines)) return(list(status = "changelog_missing", version = version))
  heads <- grep("^## ", lines)
  titles <- sub(" .*$", "", trimws(sub("^## ", "", lines[heads])))
  base <- sub("-rc[.][0-9]+$", "", version)
  wanted <- unique(c(version, if (!identical(base, version)) c(base, "Unreleased")))
  found <- match(wanted, titles)
  found <- found[!is.na(found)]
  if (!length(found)) return(list(status = "section_missing", version = version))
  at <- found[[1L]]
  first <- heads[[at]] + 1L
  last <- if (at < length(heads)) heads[[at + 1L]] - 1L else length(lines)
  blocks <- .desktop_program_blocks_v1(if (first <= last) lines[first:last] else character())
  if (!length(blocks)) return(list(status = "section_empty", version = version, section = titles[[at]]))
  list(status = "available", version = version, section = titles[[at]], blocks = blocks)
}

# Der kleine Ausschnitt aus Markdown, den das CHANGELOG nutzt: Absaetze, Aufzaehlungen mit "- " (Fortsetzung eingerueckt) und
# Zwischenueberschriften. Alles andere bleibt Text.
.desktop_program_blocks_v1 <- function(lines) {
  blocks <- list()
  current <- NULL
  flush <- function() {
    if (!is.null(current)) blocks[[length(blocks) + 1L]] <<- current
    current <<- NULL
  }
  for (line in lines) {
    if (!nzchar(trimws(line))) { flush(); next }
    if (grepl("^- ", line)) {
      item <- trimws(sub("^- +", "", line))
      if (!is.null(current) && identical(current$type, "list")) current$items <- c(current$items, item)
      else { flush(); current <- list(type = "list", items = item) }
    } else if (grepl("^ {2,}[^ ]", line) && !is.null(current) && !identical(current$type, "heading")) {
      text <- trimws(line)
      if (identical(current$type, "list")) current$items[[length(current$items)]] <- paste(current$items[[length(current$items)]], text)
      else current$text <- paste(current$text, text)
    } else if (grepl("^#{3,6} ", line)) {
      flush(); current <- list(type = "heading", text = trimws(sub("^#+ ", "", line))); flush()
    } else {
      text <- trimws(line)
      if (!is.null(current) && identical(current$type, "paragraph")) current$text <- paste(current$text, text)
      else { flush(); current <- list(type = "paragraph", text = text) }
    }
  }
  flush()
  blocks
}

# **fett** und `Code` als Tags, der Rest als Text: htmltools maskiert ihn, aus dem CHANGELOG gelangt kein HTML auf die Seite.
.desktop_program_inline_v1 <- function(text) {
  hits <- gregexpr("\\*\\*[^*]+\\*\\*|`[^`]+`", text, perl = TRUE)[[1L]]
  if (hits[[1L]] == -1L) return(text)
  sizes <- attr(hits, "match.length")
  parts <- list()
  position <- 1L
  for (index in seq_along(hits)) {
    start <- hits[[index]]
    end <- start + sizes[[index]] - 1L
    if (start > position) parts[[length(parts) + 1L]] <- substr(text, position, start - 1L)
    token <- substr(text, start, end)
    parts[[length(parts) + 1L]] <- if (startsWith(token, "**")) shiny::tags$strong(substr(token, 3L, nchar(token) - 2L)) else shiny::tags$code(substr(token, 2L, nchar(token) - 1L))
    position <- end + 1L
  }
  if (position <= nchar(text)) parts[[length(parts) + 1L]] <- substr(text, position, nchar(text))
  do.call(shiny::tagList, parts)
}

desktop_program_notes_missing_text_v1 <- function(changelog) {
  status <- if (is.list(changelog) && is.character(changelog$status) && length(changelog$status) == 1L) changelog$status else "version_unknown"
  version <- if (is.list(changelog) && is.character(changelog$version)) changelog$version else ""
  switch(status,
    changelog_missing = "Nicht verfügbar: Dieses Programm bringt keine Versionshinweise mit.",
    section_missing = paste0("Nicht verfügbar: Die Versionshinweise haben keinen Abschnitt für Version ", version, "."),
    section_empty = paste0("Nicht verfügbar: Der Abschnitt für Version ", version, " in den Versionshinweisen ist leer."),
    "Nicht verfügbar: Die Versionsangabe dieses Programms ist nicht lesbar.")
}

# „Neu in dieser Version“ als Liste; fehlt der Abschnitt, steht der Grund da.
desktop_program_notes_ui_v1 <- function(changelog) {
  if (!is.list(changelog) || !identical(changelog$status, "available")) {
    return(shiny::p(class = "pl-field-hint", desktop_program_notes_missing_text_v1(changelog)))
  }
  shiny::div(class = "pl-program-notes", lapply(changelog$blocks, function(block) {
    if (identical(block$type, "list")) shiny::tags$ul(lapply(block$items, function(item) shiny::tags$li(.desktop_program_inline_v1(item))))
    else if (identical(block$type, "heading")) shiny::tags$h4(.desktop_program_inline_v1(block$text))
    else shiny::p(.desktop_program_inline_v1(block$text))
  }))
}

DESKTOP_PROGRAM_CSS_V1 <- paste0(
  ".pl-activity-program .pl-activity-line{display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline}",
  ".pl-activity-link{color:#dbe8e1;text-decoration:underline;text-underline-offset:2px}.pl-activity-link:hover,.pl-activity-link:focus{color:#fff}",
  ".pl-activity-link.disabled{opacity:.6;text-decoration:none;cursor:default}",
  ".pl-program-notes ul{padding-left:20px;margin:6px 0}.pl-program-notes li{margin:4px 0;line-height:1.45}.pl-program-notes h4{margin:12px 0 4px}",
  ".pl-program-notice{display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline;margin-top:4px}",
  ".pl-program-release-notes{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.88rem;line-height:1.5;margin:6px 0 12px;padding:10px 12px;border-left:3px solid var(--pl-line);background:var(--pl-surface-soft)}")

# Zeile im Block links (#562): laufende Version und der Weg zu „Neu in dieser Version“. `notes_action` fuehrt in Data zum Reiter
# „Programm“ der Einstellungen; Cockpit, Steuer und Analyse verlinken dorthin (#pl-open=program).
desktop_program_sidebar_ui_v1 <- function(version, notes_action = NULL) {
  known <- is.character(version) && length(version) == 1L && !is.na(version)
  shiny::div(class = "pl-activity-seg pl-activity-program",
    shiny::tags$style(shiny::HTML(DESKTOP_PROGRAM_CSS_V1)),
    shiny::div(class = "pl-activity-line pl-activity-muted",
      shiny::span(class = "pl-program-version", if (known) paste("Portelyra", version) else "Version nicht verfügbar"),
      notes_action),
    # Meldung einer neueren Version (#562 Paket 3), aus update-status.json; leer ohne Fund.
    shiny::uiOutput("pl_program_notice"))
}

# Update-Suche (#562 Paket 3), nur lesend: Ergebnis aus <home>/update-status.json, das nur der Kern (scripts/desktop_update.py) schreibt.
# Sortierschluessel einer Version wie im Kern der Update-Suche (migrations/reference/desktop_update_v1.py): die fertige Version liegt hinter
# ihren Vorabversionen. NULL, wenn die Form nicht passt.
desktop_program_version_key_v1 <- function(text) {
  if (!is.character(text) || length(text) != 1L || is.na(text)) return(NULL)
  match <- regmatches(text, regexec("^v?(0|[1-9][0-9]{0,3})[.](0|[1-9][0-9]{0,3})[.](0|[1-9][0-9]{0,3})(-rc[.](0|[1-9][0-9]{0,4}))?$", text))[[1L]]
  if (!length(match)) return(NULL)
  rc <- nzchar(match[[5L]])
  c(as.numeric(match[2:4]), if (rc) 0 else 1, if (rc) as.numeric(match[[6L]]) else 0)
}
desktop_program_version_newer_v1 <- function(candidate, running) {
  a <- desktop_program_version_key_v1(candidate); b <- desktop_program_version_key_v1(running)
  if (is.null(a) || is.null(b)) return(FALSE)
  difference <- which(a != b)
  length(difference) > 0L && a[[difference[[1L]]]] > b[[difference[[1L]]]]
}

# Ergebnis der letzten Update-Suche (<home>/update-status.json, geschrieben nur vom Kern). Ein symbolischer Link, eine unlesbare Datei oder
# ein anderer Vertrag gelten als "keine Suche". Gelesen wird die Datei selbst, nie eine Adresse.
desktop_update_status_read_v1 <- function(home) {
  if (!is.character(home) || length(home) != 1L || is.na(home) || !nzchar(home)) return(NULL)
  path <- file.path(home, "update-status.json")
  link <- Sys.readlink(path)
  if (!file.exists(path) || isTRUE(!is.na(link) && nzchar(link))) return(NULL)
  size <- file.info(path)$size
  if (is.na(size) || size > 4e6) return(NULL)
  text <- tryCatch(readChar(path, size, useBytes = TRUE), error = function(error) NULL)
  value <- if (is.character(text)) tryCatch(jsonlite::parse_json(enc2utf8(text), simplifyVector = FALSE), error = function(error) NULL) else NULL
  if (!is.list(value) || !identical(value$contract_version, "desktop_update_status_v1")) return(NULL)
  value
}

# Neuere Versionen, die die Suche uebergehen musste, weil das Archiv fehlt oder falsch heisst (`archive_missing`; Festlegung 25.11.2026:
# ein Namensfehler beim Veroeffentlichen soll nicht still „aktuell“ melden). Aufsteigend; ein Stand von vor einem Update faellt heraus.
desktop_update_skipped_newer_v1 <- function(status, running) {
  skipped <- if (is.list(status) && is.list(status$skipped)) status$skipped else list()
  versions <- unlist(lapply(skipped, function(item) {
    if (is.list(item) && identical(item$reason, "archive_missing") && desktop_program_version_newer_v1(item$version, running)) item$version
  }), use.names = FALSE)
  versions <- unique(as.character(versions))
  if (length(versions) < 2L) return(versions)
  keys <- lapply(versions, desktop_program_version_key_v1)
  versions[do.call(order, lapply(seq_along(keys[[1L]]), function(index) vapply(keys, `[[`, numeric(1L), index)))]
}

# Meldung im Block links: nur, wenn die gefundene Version neuer ist als die laufende - nach einem Update verschwindet sie von selbst. Ohne
# angebotene Version, aber mit einer uebergangenen neueren: „Version … nicht einspielbar“ (offered = FALSE).
desktop_update_notice_v1 <- function(status, running) {
  if (!is.list(status)) return(NULL)
  if (identical(status$result, "available") && desktop_program_version_newer_v1(status$version, running))
    return(list(version = status$version, checked_at_utc = status$checked_at_utc, offered = TRUE))
  skipped <- desktop_update_skipped_newer_v1(status, running)
  if (!length(skipped)) return(NULL)
  list(version = skipped[[length(skipped)]], checked_at_utc = status$checked_at_utc, offered = FALSE)
}

desktop_program_notice_ui_v1 <- function(notice, action = NULL) {
  if (is.null(notice)) return(NULL)
  shiny::div(class = "pl-activity-line pl-activity-warning pl-program-notice", role = "status",
    shiny::strong(paste0("Version ", notice$version, if (isFALSE(notice$offered)) " nicht einspielbar" else " verfügbar")), action)
}

# In jeder App: die Meldung aus der Statusdatei, alle 60 Sekunden ueber den Zeitstempel der Datei nachgesehen (gelesen wird nur bei einer
# Aenderung). `action`: in Data der Weg zum Reiter „Programm“, sonst ein Link dorthin.
desktop_program_server_v1 <- function(input, output, session, home, version, action = NULL, every_ms = 60000L) {
  path <- if (is.character(home) && length(home) == 1L && !is.na(home) && nzchar(home)) file.path(home, "update-status.json") else ""
  status <- shiny::reactivePoll(every_ms, session,
    checkFunc = function() if (nzchar(path)) paste(file.info(path)$mtime, file.info(path)$size) else "",
    valueFunc = function() desktop_update_status_read_v1(home))
  output$pl_program_notice <- shiny::renderUI(desktop_program_notice_ui_v1(desktop_update_notice_v1(status(), version), action))
  invisible(status)
}

# Der genaue Grund einer gescheiterten Suche, in Alltagssprache (Codes aus migrations/reference/desktop_update_v1.py).
desktop_update_failure_text_v1 <- function(failure) {
  code <- if (is.list(failure) && is.character(failure$code) && length(failure$code) == 1L) failure$code else if (is.character(failure) && length(failure) == 1L) failure else ""
  http <- if (is.list(failure) && is.numeric(failure$http_status)) as.integer(failure$http_status) else NA_integer_
  retry <- if (is.list(failure) && is.character(failure$retry_after_utc)) failure$retry_after_utc else NA_character_
  switch(code,
    update_source_unreachable = "GitHub ist nicht erreichbar. Besteht eine Verbindung zum Internet?",
    update_source_timeout = "GitHub hat nicht innerhalb von 15 Sekunden geantwortet. Bitte später noch einmal versuchen.",
    update_source_not_found = "GitHub kennt die Versionsliste von Portelyra nicht (Antwort 404): Das Repository ist umgezogen oder nicht öffentlich.",
    update_source_rate_limited = paste0("GitHub nimmt von Ihrer Internetadresse gerade keine Abfragen an (Abfragelimit). ",
      if (!is.na(retry)) paste0("Wieder möglich ab ", pl_moment_v1(retry), " Uhr.") else "Bitte später noch einmal versuchen."),
    update_source_failed = if (!is.na(http)) paste0("GitHub hat mit einem Fehler geantwortet (HTTP ", http, ").") else "Die Abfrage bei GitHub ist gescheitert.",
    update_source_too_large = "Die Antwort von GitHub war größer als erwartet und wurde verworfen.",
    update_source_invalid = "Die Antwort von GitHub war nicht lesbar.",
    update_version_unknown = "Die Versionsangabe dieses Programms ist nicht lesbar; ohne sie lässt sich nicht vergleichen.",
    update_consent_missing = "Automatisch wird nur mit Ihrer Zustimmung gesucht.",
    update_not_due = "Heute wurde schon gesucht; automatisch höchstens einmal am Tag.",
    # Herunterladen (#562 Paket 4)
    update_download_not_offered = "Diese Version wird gerade nicht angeboten. Bitte noch einmal „Nach Updates suchen“.",
    update_download_not_found = "Das Archiv fehlt bei GitHub (Antwort 404).",
    update_download_failed = "GitHub hat das Archiv nicht geliefert; nichts wurde eingespielt.",
    update_download_timeout = "Das Herunterladen dauerte zu lange und wurde abgebrochen; nichts wurde eingespielt.",
    update_download_unreachable = "GitHub ist beim Herunterladen nicht erreichbar. Besteht eine Verbindung zum Internet?",
    update_download_size_mismatch = "Das Archiv hat nicht die angekündigte Größe und wurde verworfen.",
    update_download_digest_mismatch = "Die Prüfsumme des Archivs stimmt nicht mit der Angabe bei GitHub überein; es wurde verworfen.",
    paste0("Die Suche ließ sich nicht starten", if (nzchar(code)) paste0(" (", code, ")") else "", "."))
}

# Lizenzhinweis (#590, Festlegung 26.11.2026): Copyright, das Recht zur Weitergabe und Veraenderung, keine Gewaehrleistung
# und der Weg zum Lizenztext - die „Appropriate Legal Notices“ der AGPL (Abschnitt 0). Zeigt das Original sie, muessen veraenderte Fassungen
# sie weiter zeigen (Abschnitt 5 d). Im Reiter „Programm“ der Daten-App; die Hilfe aller vier Apps hat die Seite „Lizenz“ (docs/handbuch/lizenz.md).
DESKTOP_LICENSE_COPYRIGHT_V1 <- "Copyright © 2026 NikoBerlin"
DESKTOP_LICENSE_URL_V1 <- "https://www.gnu.org/licenses/agpl-3.0.html"
DESKTOP_SOURCE_URL_V1 <- "https://github.com/NikoBerlin/portelyra"

# Der Lizenztext aus dem Programmordner (ab 0.3.4 im Archiv); NULL, wenn er fehlt oder unlesbar ist.
desktop_license_text_v1 <- function(project_root) {
  if (!is.character(project_root) || length(project_root) != 1L || is.na(project_root)) return(NULL)
  path <- file.path(project_root, "LICENSE")
  if (!file.exists(path)) return(NULL)
  text <- tryCatch(paste(readLines(path, encoding = "UTF-8", warn = FALSE), collapse = "\n"), error = function(error) NULL)
  if (is.null(text) || !nzchar(trimws(text))) NULL else text
}

desktop_license_notice_ui_v1 <- function() {
  link <- function(href, label) shiny::tags$a(href = href, target = "_blank", rel = "noopener noreferrer", label)
  shiny::tagList(
    shiny::p(shiny::strong("Portelyra"), paste0(" · ", DESKTOP_LICENSE_COPYRIGHT_V1)),
    shiny::p(paste("Portelyra ist freie Software: Sie dürfen es unter den Bedingungen der GNU Affero General Public License (AGPL), wie von",
                   "der Free Software Foundation veröffentlicht, weitergeben und verändern – nach Version 3 der Lizenz oder, nach Ihrer Wahl,",
                   "jeder späteren Version.")),
    shiny::p(paste("Portelyra wird in der Hoffnung bereitgestellt, dass es nützlich ist, aber ohne jede Gewährleistung, auch ohne die",
                   "stillschweigende Gewährleistung der Marktreife oder der Eignung für einen bestimmten Zweck, soweit das Gesetz es zulässt",
                   "(Abschnitte 15 und 16 der Lizenz).")),
    shiny::p("Den vollständigen Lizenztext zeigt der Knopf unten. Er liegt im Programmordner als Datei LICENSE und steht unter ",
             link(DESKTOP_LICENSE_URL_V1, "gnu.org"), ". Quelltext: ", link(DESKTOP_SOURCE_URL_V1, "github.com/NikoBerlin/portelyra"), "."),
    shiny::p(class = "pl-field-hint", "Der Name „Portelyra“ und die Bildmarke sind nicht Teil der Lizenz (Abschnitt 7 Buchstabe e)."))
}
