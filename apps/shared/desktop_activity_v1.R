# Der Block links in allen vier Apps (#540, rc.366, Festlegung 05.11.2026): Aktualisierung, „Läuft gerade“ und Einstellungen.
#
# - Aktualisierung: ob gerade ein Lauf rechnet, seit wann (zaehlt im Browser hoch), welcher Schritt, wie weit und wie lange noch
#   (aus der Dauer des letzten Laufs); wann zuletzt einer fertig wurde und wann der naechste geplant ist.
# - Läuft gerade: je Vorgang eine Zeile - der Sammellauf im Reiter Marktdaten, eine Wartung, und ein langer Vorgang dieser Seite
#   (der Hinweis aus #457, gespiegelt im Browser).
# - Einstellungen: ein Eintrag. In der Data-App klappen beide Knoepfe die Bereiche auf; in Cockpit, Steuer und Analyse fuehren sie
#   nach Data (#pl-open=refresh|settings - die Adresse selbst muss der Startpruefung wegen unveraendert bleiben).
#
# Der ausfuehrliche Fortschritt bleibt dort, wo geklickt wurde. Cockpit, Steuer und Analyse lesen den veroeffentlichten Stand
# (contracts/activity-status/v1): Alle paar Sekunden wird nur der Zeiger latest.json angesehen; gelesen wird erst, wenn er sich
# aendert. Die Data-App bildet den Stand direkt (apps/data/data_activity_status_v1.R). Fehlende Angaben erscheinen nicht als 0.

# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
DESKTOP_ACTIVITY_KIND_WORDS_V1 <- c(refresh = "Alles aktualisieren", moment = "Momentaufnahme", sweep = "Sammellauf im Reiter Marktdaten",
                                    names = "Datenbasis neu veröffentlichen", maintenance = "Wartung (Backup oder Upgrade)", other = "Ein Lauf")
DESKTOP_ACTIVITY_AREA_V1 <- "activity_status"

.desktop_activity_time_v1 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value)) return(NA)
  suppressWarnings(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
}

# „heute 09:15“, „gestern 18:40“, „morgen 09:15“ oder „03.11. 09:15“ - in Ortszeit.
desktop_activity_when_v1 <- function(time, now = Sys.time()) {
  if (length(time) != 1L || is.na(time)) return("–")
  tz <- ""
  day <- as.Date(format(time, "%Y-%m-%d", tz = tz)); today <- as.Date(format(now, "%Y-%m-%d", tz = tz))
  prefix <- if (day == today) "heute" else if (day == today - 1L) "gestern" else if (day == today + 1L) "morgen" else format(day, "%d.%m.")
  paste(prefix, format(time, "%H:%M", tz = tz))
}

# Dauer in Worten: „unter 1 Min.“, „18 Min.“, „1:05 Std.“.
desktop_activity_duration_v1 <- function(seconds) {
  seconds <- suppressWarnings(as.numeric(seconds))
  if (length(seconds) != 1L || is.na(seconds) || seconds < 0) return(NULL)
  if (seconds < 60) return("unter 1 Min.")
  minutes <- round(seconds / 60)
  if (minutes < 90) return(paste(minutes, "Min."))
  sprintf("%d:%02d Std.", minutes %/% 60L, minutes %% 60L)
}

# Der naechste Termin aus den Uhrzeiten des Zeitplans (Ortszeit, wie der systemd-Timer).
desktop_activity_next_at_v1 <- function(times, now = Sys.time()) {
  times <- as.character(unlist(times))
  times <- times[grepl("^([01][0-9]|2[0-3]):[0-5][0-9]$", times)]
  if (!length(times)) return(NA)
  tz <- ""; today <- as.Date(format(now, "%Y-%m-%d", tz = tz))
  candidates <- as.POSIXct(paste(rep(format(c(today, today + 1L)), each = length(times)), rep(times, 2L)), format = "%Y-%m-%d %H:%M", tz = tz)
  candidates <- sort(candidates[!is.na(candidates) & as.numeric(candidates) > as.numeric(now)])
  if (length(candidates)) candidates[[1L]] else NA
}

.desktop_activity_line_v1 <- function(..., class = NULL) shiny::div(class = paste(c("pl-activity-line", class), collapse = " "), ...)

# Ein laufender Lauf von „Alles aktualisieren“ oder der Momentaufnahme.
.desktop_activity_run_view_v1 <- function(row, now) {
  started <- .desktop_activity_time_v1(row$started_at_utc)
  what <- if (identical(row$kind, "moment")) "Momentaufnahme läuft" else "Läuft"
  elapsed <- if (!is.na(started)) max(0L, as.integer(as.numeric(difftime(now, started, units = "secs")))) else NA_integer_
  since <- if (!is.na(started)) shiny::tagList(" seit ", format(started, "%H:%M", tz = ""), " · ",
    shiny::span(class = "pl-elapsed", `data-since` = sprintf("%.0f", as.numeric(started) * 1000), sprintf("%d:%02d", elapsed %/% 60L, elapsed %% 60L))) else NULL
  step <- if (!is.null(row$step_label)) paste0(
    if (!is.null(row$step_position) && !is.null(row$step_count)) paste0("Schritt ", row$step_position, " von ", row$step_count, " · ") else "",
    row$step_label, if (!is.null(row$total)) paste0(" · ", row$done, " von ", row$total) else "") else NULL
  end <- .desktop_activity_time_v1(row$expected_end_utc)
  shiny::tagList(
    .desktop_activity_line_v1(class = "pl-activity-live", shiny::span(class = "pl-activity-dot", `aria-hidden` = "true"),
      shiny::strong(what), since, if (identical(row$origin, "timer")) " · zeitgesteuert" else NULL),
    if (!is.null(step)) .desktop_activity_line_v1(step) else NULL,
    if (!is.null(row$total) && as.integer(row$total) > 0L) shiny::tags$progress(class = "pl-activity-bar", max = as.integer(row$total),
      value = as.integer(row$done), `aria-label` = paste(row$done, "von", row$total)) else NULL,
    .desktop_activity_line_v1(class = "pl-activity-muted", if (!is.na(end))
      shiny::span(`data-until` = sprintf("%.0f", as.numeric(end) * 1000), desktop_activity_rest_v1(as.numeric(difftime(end, now, units = "secs"))))
      else "Restdauer noch nicht bekannt"))
}

# Restzeit in Worten - dieselbe Rechnung wie im Browser (Huelle, data-until), der sie jede Sekunde nachzieht.
desktop_activity_rest_v1 <- function(seconds) {
  if (seconds < -60) return("dauert länger als der letzte Lauf")
  if (seconds < 60) return("≈ unter 1 Min. Rest")
  paste0("≈ ", desktop_activity_duration_v1(seconds), " Rest")
}

.desktop_activity_last_view_v1 <- function(last, label, now) {
  if (!is.list(last)) return(.desktop_activity_line_v1(class = "pl-activity-muted", paste0(label, ": noch keiner")))
  at <- desktop_activity_when_v1(.desktop_activity_time_v1(last$finished_at_utc), now)
  took <- desktop_activity_duration_v1(last$seconds)
  good <- identical(last$tone, "positive")
  .desktop_activity_line_v1(class = if (identical(last$tone, "error")) "pl-activity-error" else if (identical(last$tone, "warning")) "pl-activity-warning" else NULL,
    paste0(label, ": ", at, if (!is.null(took)) paste0(" · ", took) else "", if (!good) paste0(" · ", last$title) else ""))
}

.desktop_activity_next_view_v1 <- function(planned, now) {
  part <- function(value, label) {
    if (!is.list(value) || !isTRUE(value$enabled)) return(NULL)
    at <- desktop_activity_next_at_v1(value$times, now)
    if (is.na(at)) NULL else paste0(label, desktop_activity_when_v1(at, now))
  }
  parts <- c(part(planned$refresh, "Nächster Lauf: "), part(planned$moment, "Momentaufnahme: "))
  .desktop_activity_line_v1(class = "pl-activity-muted", if (length(parts)) paste(parts, collapse = " · ") else "Kein Zeitplan eingeschaltet")
}

# Segment „Aktualisierung“: status ist der gelesene Stand (status = "available" | "absent" | "failed").
desktop_activity_refresh_view_v1 <- function(status, now = Sys.time()) {
  if (is.null(status)) return(.desktop_activity_line_v1(class = "pl-activity-muted", "Stand wird gelesen …"))
  if (!is.list(status) || identical(status$status, "failed"))
    return(.desktop_activity_line_v1(class = "pl-activity-muted", "Stand der Aktualisierung nicht lesbar."))
  if (identical(status$status, "absent"))
    return(.desktop_activity_line_v1(class = "pl-activity-muted", "Noch kein Stand veröffentlicht. Er erscheint mit dem nächsten Lauf oder beim Öffnen der App „Daten“."))
  runs <- Filter(function(row) isTRUE(row$kind %in% c("refresh", "moment")), status$running)
  shiny::tagList(
    if (length(runs)) .desktop_activity_run_view_v1(runs[[1L]], now) else NULL,
    .desktop_activity_last_view_v1(status$last$refresh, "Zuletzt fertig", now),
    if (is.list(status$last$moment) || isTRUE(status$`next`$moment$enabled)) .desktop_activity_last_view_v1(status$last$moment, "Momentaufnahme", now) else NULL,
    .desktop_activity_next_view_v1(status$`next`, now))
}

# Segment „Läuft gerade“: alles, was ausser einem Lauf von „Alles aktualisieren“ sperrt.
desktop_activity_running_view_v1 <- function(status, now = Sys.time()) {
  rows <- if (is.list(status) && identical(status$status, "available")) Filter(function(row) !isTRUE(row$kind %in% c("refresh", "moment")), status$running) else list()
  if (!length(rows)) return(.desktop_activity_line_v1(class = "pl-activity-muted pl-activity-idle", "Nichts im Hintergrund."))
  shiny::tagList(lapply(rows, function(row) {
    started <- .desktop_activity_time_v1(row$started_at_utc)
    word <- DESKTOP_ACTIVITY_KIND_WORDS_V1[[if (isTRUE(row$kind %in% names(DESKTOP_ACTIVITY_KIND_WORDS_V1))) row$kind else "other"]]
    .desktop_activity_line_v1(class = "pl-activity-live", shiny::span(class = "pl-activity-dot", `aria-hidden` = "true"), paste0(word,
      if (!is.na(started)) paste0(" · seit ", format(started, "%H:%M", tz = "")) else "",
      if (!is.null(row$total)) paste0(" · ", row$done, " von ", row$total) else ""))
  }))
}

# Adresse der Data-App - wie in der Navigation (portelyra_navigation).
desktop_activity_data_url_v1 <- function() {
  url <- Sys.getenv("PORTELYRA_APP_URL_DATA", unset = "")
  ports <- getOption("portelyra.desktop.ports")
  if (!nzchar(url) && !is.null(ports) && "data" %in% names(ports)) url <- paste0("http://127.0.0.1:", as.integer(ports[["data"]]))
  url
}

# Ein Knopf, der nach Data fuehrt und dort den Bereich aufklappt. Den Startschluessel haengt die Huelle an (data-portelyra-nav).
desktop_activity_data_link_v1 <- function(target, label, class = "btn btn-default") {
  url <- desktop_activity_data_url_v1()
  if (!nzchar(url)) return(shiny::tags$span(class = paste(class, "disabled"), `aria-disabled` = "true", title = "Die App „Daten“ ist nicht erreichbar.", label))
  shiny::tags$a(class = class, href = paste0(url, "#pl-open=", target), `data-portelyra-nav` = "app", label)
}

# refresh_action, settings_action: in Data die Knoepfe zum Aufklappen, sonst Links nach Data. version (#562, 0.3.3): die laufende Version
# fuer die Zeile ganz unten und die Hilfe (apps/shared/desktop_program_v1.R); notes_action fuehrt zu „Neu in dieser Version“ - in Data
# zum Reiter „Programm“, sonst als Link dorthin.
# tour (#578): nur im Demo der Rundgang mit dem Knopf „Rundgang starten“ (apps/shared/desktop_tour_v1.R); das Startskript setzt dort die
# Option portelyra.desktop.demo.
desktop_activity_sidebar_ui_v1 <- function(refresh_action = desktop_activity_data_link_v1("refresh", "Alles aktualisieren", "btn btn-primary"),
                                           settings_action = desktop_activity_data_link_v1("settings", "Einstellungen"), help_app = NULL,
                                           version = NULL, notes_action = desktop_activity_data_link_v1("program", "Neu in dieser Version", "pl-activity-link"),
                                           tour = isTRUE(getOption("portelyra.desktop.demo"))) {
  shiny::tags$section(class = "pl-activity", `aria-label` = "Aktualisierung und Einstellungen",
    shiny::div(class = "pl-activity-seg",
      shiny::div(class = "pl-activity-head", "Aktualisierung"),
      shiny::div(role = "status", `aria-live` = "polite", shiny::uiOutput("pl_activity_refresh")),
      shiny::div(class = "pl-activity-actions", refresh_action)),
    shiny::div(class = "pl-activity-seg pl-activity-running",
      shiny::div(class = "pl-activity-head", "Läuft gerade"),
      shiny::uiOutput("pl_activity_running"),
      # Ein langer Vorgang dieser Seite (#457) - gespiegelt vom Hinweis der Huelle, ohne Server.
      shiny::div(class = "pl-activity-line pl-activity-session", hidden = NA)),
    # Umfang je Portfolio (#542): eine Zeile, nur bei veroeffentlichtem Umfang - leer nimmt der Platz keinen Raum ein.
    shiny::div(class = "pl-activity-seg", shiny::uiOutput("pl_activity_scope", class = "pl-scope-slot"),
      shiny::div(class = "pl-activity-actions", settings_action)),
    # Hilfe (#488, rc.436): oeffnet das Handbuch beim Abschnitt des offenen Reiters (apps/shared/desktop_help_v1.R).
    if (!is.null(help_app)) desktop_help_ui_v1(help_app, version),
    if (isTRUE(tour)) desktop_tour_ui_v1(),
    # Portelyra beenden (#570): erscheint nur, wenn diese App wirklich vom Startskript gestartet wurde.
    shiny::div(class = "pl-activity-seg pl-activity-quit", shiny::uiOutput("pl_activity_quit")),
    # Version und „Neu in dieser Version“ (#562): zuletzt, in allen vier Apps.
    if (!is.null(version)) desktop_program_sidebar_ui_v1(version, notes_action))
}

# „Portelyra beenden“ links in jeder App (#570, rc.433; Festlegung 18.11.2026). Die Apps laufen als Kindprozesse des Startskripts; ihm
# geht ein SIGINT, dann haelt es alle Apps an, sperrt den Bestand und gibt zuletzt die Sitzungssperre frei - wie `stop`. Nur wenn der
# Elternprozess wirklich ein Start ist (sonst kein Knopf, etwa unter dev/start_dev.R oder in testServer). Arbeitet eine App gerade (ein
# Kindprozess einer App: Buchung, Import, Backup), wird nicht beendet.
desktop_quit_controller_v1 <- function(proc = "/proc") {
  stat_field <- function(pid, index) {
    line <- suppressWarnings(tryCatch(readLines(file.path(proc, pid, "stat"), warn = FALSE, n = 1L), error = function(error) character()))
    if (length(line) != 1L) return(NA_character_)
    positions <- gregexpr(") ", line, fixed = TRUE)[[1L]]; positions <- positions[positions > 0L]
    if (!length(positions)) return(NA_character_)
    fields <- strsplit(substring(line, positions[[length(positions)]] + 2L), " ", fixed = TRUE)[[1L]]
    if (length(fields) < index) NA_character_ else fields[[index]]
  }
  command_of <- function(pid) {
    raw <- tryCatch(readBin(file.path(proc, pid, "cmdline"), "raw", 65536L), error = function(error) raw())
    if (!length(raw)) "" else rawToChar(replace(raw, raw == as.raw(0L), as.raw(32L)))
  }
  start_pid <- stat_field(as.character(Sys.getpid()), 2L)
  start_command <- if (is.na(start_pid)) "" else command_of(start_pid)
  available <- !is.na(start_pid) && start_pid != "1" && grepl("--file=.*portelyra_desktop[.]R --args start( |$)", start_command)
  busy <- function() {
    if (!available) return(FALSE)
    pids <- basename(Sys.glob(file.path(proc, "[0-9]*")))
    parents <- vapply(pids, function(pid) stat_field(pid, 2L), character(1L))
    apps <- pids[!is.na(parents) & parents == start_pid]
    apps <- apps[vapply(apps, function(pid) identical(command_of(pid), start_command), logical(1L))]
    any(!is.na(parents) & parents %in% apps)
  }
  list(available = function() available, busy = busy,
       stop = function(delay = 2) later::later(function() tools::pskill(as.integer(start_pid), tools::SIGINT), delay))
}

desktop_quit_view_v1 <- function(state) {
  switch(state,
    ask = shiny::tagList(
      shiny::div(class = "pl-activity-line", "Beendet alle vier Apps. Zeitpläne laufen weiter."),
      shiny::div(class = "pl-activity-actions",
        shiny::actionButton("pl_quit_confirm", "Jetzt beenden", class = "btn btn-primary"),
        shiny::actionButton("pl_quit_cancel", "Abbrechen", class = "btn btn-default"))),
    busy = shiny::tagList(
      shiny::div(class = "pl-activity-line", role = "status",
                 "Portelyra arbeitet gerade, etwa an einer Buchung oder einem Import. Bitte kurz warten und erneut beenden."),
      shiny::div(class = "pl-activity-actions", shiny::actionButton("pl_quit_ask", "Portelyra beenden", class = "btn btn-default"))),
    stopping = shiny::div(class = "pl-activity-line", role = "status", "Portelyra wird beendet. Dieses Fenster kann danach geschlossen werden."),
    shiny::div(class = "pl-activity-actions", shiny::actionButton("pl_quit_ask", "Portelyra beenden", class = "btn btn-default")))
}

# Umfang je Portfolio (#542, Festlegung 06.11. und 10.11.2026): Die Anzeige-Apps lesen ihn aus den veroeffentlichten
# Anzeige-Einstellungen (spotdisplay::read_display_settings_latest_v1). Er zaehlt nur, wenn er veroeffentlicht ist; sonst gilt alles
# wie bisher (source = "default"). Haekchen steuern Angebot und Ablaeufe, nicht die Rechnung - hier wird nur benannt und ausgeblendet.
desktop_scope_of_v1 <- function(settings) {
  scope <- if (is.list(settings)) settings$portfolio_scope else NULL
  if (is.list(scope) && identical(scope$source, "published") && is.list(scope$modules)) scope else NULL
}
# Ein Baustein ist nur aus, wenn ein veroeffentlichter Umfang ihn ausdruecklich abschaltet.
desktop_scope_off_v1 <- function(scope, module) is.list(scope) && isFALSE(scope$modules[[module]])
desktop_scope_modules_v1 <- function(scope) if (is.list(scope) && is.list(scope$modules)) scope$modules else NULL
# Der Umfang eines einzelnen Portfolios aus dem veroeffentlichten Umfang (rc.410): Dieser fuehrt die Bausteine nur fuer den ganzen
# Datenraum (an, sobald irgendein aktives Portfolio sie nutzt). Eindeutig ist das nur bei genau einem aktiven Portfolio; sonst NULL.
desktop_scope_single_portfolio_modules_v1 <- function(scope) {
  if (!is.list(scope) || !is.list(scope$modules) || !is.list(scope$portfolios)) return(NULL)
  active <- Filter(function(row) is.list(row) && identical(row$status, "active"), scope$portfolios)
  if (length(active) == 1L) scope$modules else NULL
}

# „Umfang: …“ im Block links - der wirksame Umfang des Datenraums, wie ihn der Kern in Worte fasst.
desktop_activity_scope_view_v1 <- function(scope) {
  text <- if (is.list(scope)) scope$effective_scope_text else NULL
  if (!is.character(text) || length(text) != 1L || is.na(text) || !nzchar(text)) return(NULL)
  .desktop_activity_line_v1(class = "pl-activity-scope", shiny::span(class = "pl-activity-muted", "Umfang: "), text)
}
# scope: eine reaktive Funktion, die den veroeffentlichten Umfang liefert (oder NULL).
desktop_activity_scope_server_v1 <- function(output, scope) {
  output$pl_activity_scope <- shiny::renderUI(desktop_activity_scope_view_v1(scope()))
  # Leer ausgeblendet (.pl-scope-slot:empty): ohne diese Angabe gaelte der Platz im Browser als verborgen und wuerde nie berechnet.
  shiny::outputOptions(output, "pl_activity_scope", suspendWhenHidden = FALSE)
  invisible(NULL)
}

# Lesen fuer Cockpit, Steuer und Analyse: marker ist billig (Groesse und Zeit von latest.json), read ruft die CLI mit der Rolle
# der App. Ein Fehler zeigt „nicht lesbar“, nie einen erfundenen Stand.
desktop_activity_reader_v1 <- function(project_root, context, role, runner = NULL) {
  space <- file.path(context$data_root, context$tenant_id, context$user_id, context$data_space_id)
  latest <- file.path(space, "artifacts", DESKTOP_ACTIVITY_AREA_V1, "latest.json")
  python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "desktop_activity_status.py")
  payload <- list(context = list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id),
                  data_space_path = space, role = role)
  run <- runner %||% function(payload) {
    if (!nzchar(python) || !file.exists(cli)) return(list(status = "blocked"))
    encoded <- as.character(jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", digits = NA))
    output <- tryCatch(suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), "read"), stdout = TRUE, stderr = FALSE, input = encoded)),
                       error = function(error) character())
    tryCatch(jsonlite::fromJSON(output[[length(output)]], simplifyVector = FALSE), error = function(error) list(status = "blocked"))
  }
  list(
    marker = function() { info <- file.info(latest); if (is.na(info$size)) "absent" else paste(info$size, format(as.numeric(info$mtime), nsmall = 3)) },
    read = function() {
      result <- tryCatch(run(payload), error = function(error) NULL)
      if (is.list(result) && identical(result$status, "completed") && is.list(result$value)) result$value else list(status = "failed")
    })
}

# source: list(marker, read). Solange etwas laeuft, alle `busy_ms`, sonst alle `idle_ms` den Zeiger ansehen. Zum ersten Mal erst
# `first_ms` nach dem Start: Das Lesen ruft in den Anzeige-Apps Python auf und gehoert nicht in den Sitzungsstart.
desktop_activity_server_v1 <- function(input, output, session, source, busy_ms = 3000L, idle_ms = 10000L, first_ms = 400L,
                                       quitter = desktop_quit_controller_v1()) {
  status <- shiny::reactiveVal(NULL)
  seen <- NULL; started <- FALSE
  busy <- function(value) is.list(value) && length(value$running) > 0L
  shiny::observe({
    if (!started) { started <<- TRUE; shiny::invalidateLater(first_ms); return() }
    marker <- tryCatch(source$marker(), error = function(error) NA_character_)
    if (is.null(seen) || !identical(marker, seen)) {
      seen <<- marker
      status(tryCatch(source$read(), error = function(error) list(status = "failed")))
    }
    shiny::invalidateLater(if (busy(shiny::isolate(status()))) busy_ms else idle_ms)
  })
  output$pl_activity_refresh <- shiny::renderUI(desktop_activity_refresh_view_v1(status()))
  output$pl_activity_running <- shiny::renderUI(desktop_activity_running_view_v1(status()))
  # Portelyra beenden (#570): fragen, dann pruefen, ob gerade etwas arbeitet, dann den Start bitten.
  quit_state <- shiny::reactiveVal("idle")
  output$pl_activity_quit <- shiny::renderUI(if (is.list(quitter) && isTRUE(quitter$available())) desktop_quit_view_v1(quit_state()))
  shiny::observeEvent(input$pl_quit_ask, quit_state("ask"), ignoreInit = TRUE)
  shiny::observeEvent(input$pl_quit_cancel, quit_state("idle"), ignoreInit = TRUE)
  shiny::observeEvent(input$pl_quit_confirm, {
    if (isTRUE(quitter$busy())) return(quit_state("busy"))
    quit_state("stopping")
    quitter$stop()
  }, ignoreInit = TRUE)
  invisible(list(status = status, quit = quit_state))
}
