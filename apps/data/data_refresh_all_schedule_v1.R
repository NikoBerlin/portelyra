# „Alles aktualisieren“ und die Momentaufnahme von selbst (rc.316, #510; mehrere Zeiten und eigener Zeitplan seit rc.365, #516).
#
# Festlegung 24.10.2026: optional mindestens einmal am Tag, Vorgabe aus. Das Einschalten ist die ausdrueckliche Zustimmung, dass
# Portelyra zur gewaehlten Uhrzeit ohne Zutun Kurse beim Anbieter abruft (nur lesend) und dieselben Staende schreibt wie der Knopf.
# Umsetzung: je Zeitplan ein systemd-Timer des Benutzers (OnCalendar je Uhrzeit, Persistent=true - ein verpasster Termin, etwa weil
# der Rechner aus war, wird beim naechsten Anmelden nachgeholt). Er startet scripts/desktop_refresh_all.R mit --origin timer; Sperre
# und Stand sind dieselben wie beim Start aus der App. Die Einstellung steht in refresh-all-v1/schedule.json, das Ergebnis des
# letzten zeitgesteuerten Laufs in last-timer.json (Momentaufnahme: last-moment-timer.json). Die Unit-Dateien liegen unter
# ~/.config/systemd/user und tragen einen Abdruck des Portelyra-Home im Namen, damit zwei Installationen sich nicht ueberschreiben.
#
# Festlegung 25.10.2026 (#516): mehrere Zeiten am Tag; ein eigener, schneller Zeitplan nur fuer die Momentaufnahme; Quellluecken
# selten statt bei jedem Lauf. Trifft ein Zeitplan auf einen laufenden Lauf, wartet er bis zu 30 Minuten (desktop_refresh_all.R).

DATA_REFRESH_ALL_SCHEDULE_TIMES_V1 <- sprintf("%02d:%02d", rep(0:23, each = 2L), rep(c(0L, 30L), 24L))
DATA_REFRESH_ALL_SCHEDULE_DEFAULT_V1 <- "07:00"
DATA_REFRESH_ALL_SCHEDULE_MAX_TIMES_V1 <- 6L
# Quellluecken erneut abfragen: bei jedem Lauf, einmal pro Woche (Vorgabe seit rc.365) oder nie.
DATA_REFRESH_ALL_SCHEDULE_GAPS_V1 <- c("Einmal pro Woche" = "weekly", "Bei jedem Lauf" = "always", "Nie" = "never")

# Bis rc.364 stand eine Uhrzeit in `time` und die Lueckenwahl als ja/nein in `retry_gaps`.
.data_refresh_all_schedule_times_of_v1 <- function(value) {
  times <- if (is.list(value) && length(value$times)) as.character(unlist(value$times)) else if (is.list(value) && is.character(value$time)) value$time else DATA_REFRESH_ALL_SCHEDULE_DEFAULT_V1
  sort(unique(times[times %in% DATA_REFRESH_ALL_SCHEDULE_TIMES_V1]))
}
.data_refresh_all_schedule_gaps_of_v1 <- function(value) {
  if (isTRUE(value)) return("always")
  if (isFALSE(value)) return("never")
  if (is.character(value) && length(value) == 1L && value %in% DATA_REFRESH_ALL_SCHEDULE_GAPS_V1) return(value)
  "weekly"
}
.data_refresh_all_schedule_valid_times_v1 <- function(times) {
  is.character(times) && length(times) >= 1L && length(times) <= DATA_REFRESH_ALL_SCHEDULE_MAX_TIMES_V1 && !anyNA(times) &&
    all(times %in% DATA_REFRESH_ALL_SCHEDULE_TIMES_V1) && !anyDuplicated(times)
}

# systemctl: Funktion (args) -> Ausgabezeilen mit Attribut status bei Fehler; ohne Angabe der echte Benutzer-Dienst.
data_refresh_all_schedule_v1 <- function(project_root, runtime, store, systemctl = NULL, unit_dir = NULL) {
  home <- normalizePath(runtime$home, winslash = "/", mustWork = TRUE)
  stamp <- substr(digest::digest(home, algo = "sha256", serialize = FALSE), 1L, 8L)
  units <- list(refresh = paste0("portelyra-refresh-all-", stamp), moment = paste0("portelyra-moment-", stamp))
  unit <- units$refresh
  if (is.null(unit_dir)) {
    config <- Sys.getenv("XDG_CONFIG_HOME", unset = "")
    if (!nzchar(config)) config <- file.path(Sys.getenv("HOME"), ".config")
    unit_dir <- file.path(config, "systemd", "user")
  }
  run <- if (is.function(systemctl)) systemctl else function(args) {
    exe <- Sys.which("systemctl")
    if (!nzchar(exe)) return(structure("systemctl fehlt", status = 127L))
    suppressWarnings(system2(exe, c("--user", args), stdout = TRUE, stderr = TRUE))
  }
  ok <- function(output) is.null(attr(output, "status")) || identical(as.integer(attr(output, "status")), 0L)
  # Doppelte Anfuehrungszeichen nach systemd-Regeln; % und $ verdoppeln, damit systemd nichts ersetzt.
  quote <- function(value) paste0('"', gsub("$", "$$", gsub("%", "%%", gsub('(["\\\\])', "\\\\\\1", value), fixed = TRUE), fixed = TRUE), '"')
  # `retry_gaps`: "always", "weekly" oder "never" (TRUE/FALSE wie bis rc.364). Die Momentaufnahme fragt keine Luecken ab.
  service_text <- function(retry_gaps, kind = "refresh") {
    gaps <- switch(.data_refresh_all_schedule_gaps_of_v1(retry_gaps), always = "yes", weekly = "weekly", never = "no")
    args <- c(file.path(R.home("bin"), "Rscript"), file.path(project_root, "scripts", "desktop_refresh_all.R"),
              "--home", home, "--run-id", "auto", "--origin", "timer",
              if (identical(kind, "moment")) c("--only", "moment", "--retry-gaps", "no") else c("--retry-gaps", gaps),
              "--confirm", "RUN_REFRESH_ALL")
    paste0("[Unit]\nDescription=Portelyra: ", if (identical(kind, "moment")) "Momentaufnahme" else "Alles aktualisieren", " (zeitgesteuert)\n\n",
           "[Service]\nType=oneshot\nUMask=0077\nEnvironment=PYTHONDONTWRITEBYTECODE=1\nExecStart=", paste(quote(args), collapse = " "), "\n")
  }
  timer_text <- function(times, kind = "refresh") {
    times <- sort(unique(as.character(times)))
    paste0("[Unit]\nDescription=Portelyra: ", if (identical(kind, "moment")) "Momentaufnahme" else "Alles aktualisieren", " täglich um ",
           paste(times, collapse = ", "), " Uhr\n\n[Timer]\n", paste0("OnCalendar=*-*-* ", times, ":00\n", collapse = ""),
           "Persistent=true\nUnit=", units[[kind]], ".service\n\n[Install]\nWantedBy=timers.target\n")
  }
  paths_of <- function(kind) list(service = file.path(unit_dir, paste0(units[[kind]], ".service")), timer = file.path(unit_dir, paste0(units[[kind]], ".timer")))
  paths <- paths_of("refresh")
  write_unit <- function(path, text) {
    temp <- paste0(path, ".tmp-", Sys.getpid())
    writeLines(text, temp, sep = "", useBytes = TRUE); Sys.chmod(temp, "0644")
    if (!file.rename(temp, path)) { unlink(temp); stop("data_refresh_all_schedule_write_failed", call. = FALSE) }
  }
  # Zeitpunkte aus `systemctl show`: "@1761372000" oder - so liefert systemd den naechsten Termin trotz --timestamp=unix -
  # Klartext in Ortszeit ("Thu 2099-01-01 00:00:00 CET"). Leer heisst: kein Termin.
  moment <- function(value) {
    if (!is.character(value) || length(value) != 1L || !nzchar(value)) return(NULL)
    if (startsWith(value, "@")) {
      seconds <- suppressWarnings(as.numeric(sub("^@", "", value)))
      return(if (is.na(seconds) || seconds <= 0) NULL else as.POSIXct(seconds, origin = "1970-01-01", tz = "UTC"))
    }
    stamp <- regmatches(value, regexpr("[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value))
    if (length(stamp) != 1L) return(NULL)
    parsed <- suppressWarnings(as.POSIXct(stamp, format = "%Y-%m-%d %H:%M:%S", tz = ""))
    if (is.na(parsed)) NULL else parsed
  }
  show <- function(kind) {
    shown <- run(c("show", paste0(units[[kind]], ".timer"), "--property=ActiveState,UnitFileState,NextElapseUSecRealtime,LastTriggerUSec", "--timestamp=unix"))
    props <- list()
    if (ok(shown)) for (line in shown) if (grepl("=", line, fixed = TRUE)) props[[sub("=.*$", "", line)]] <- sub("^[^=]*=", "", line)
    list(available = ok(shown), active = identical(props$ActiveState, "active"), next_at = moment(props$NextElapseUSecRealtime),
         last_trigger = moment(props$LastTriggerUSec))
  }
  status <- function() {
    schedule <- store$read_schedule()
    shown <- show("refresh")
    times <- .data_refresh_all_schedule_times_of_v1(schedule)
    saved_moment <- if (is.list(schedule) && is.list(schedule$moment)) schedule$moment else NULL
    moment_shown <- show("moment")
    list(available = shown$available, enabled = is.list(schedule) && isTRUE(schedule$enabled),
         time = times[[1L]], times = times, retry_gaps = .data_refresh_all_schedule_gaps_of_v1(if (is.list(schedule)) schedule$retry_gaps else NULL),
         active = shown$active, next_at = shown$next_at, last_trigger = shown$last_trigger, last = store$read_last_timer(), unit = unit,
         moment = list(enabled = is.list(saved_moment) && isTRUE(saved_moment$enabled), times = .data_refresh_all_schedule_times_of_v1(saved_moment),
                       active = moment_shown$active, next_at = moment_shown$next_at, last = store$read_last_timer("moment"), unit = units$moment))
  }
  install <- function(kind, times, retry_gaps) {
    target <- paths_of(kind)
    if (!dir.exists(unit_dir)) dir.create(unit_dir, recursive = TRUE, mode = "0755")
    write_unit(target$service, service_text(retry_gaps, kind)); write_unit(target$timer, timer_text(times, kind))
    for (args in list(c("daemon-reload"), c("enable", paste0(units[[kind]], ".timer")), c("restart", paste0(units[[kind]], ".timer")))) if (!ok(run(args))) {
      unlink(unlist(target)); invisible(run("daemon-reload"))
      return(FALSE)
    }
    TRUE
  }
  remove <- function(kind) {
    target <- paths_of(kind)
    if (file.exists(target$timer)) invisible(run(c("disable", "--now", paste0(units[[kind]], ".timer"))))
    unlink(unlist(target)); invisible(run("daemon-reload"))
  }
  saved <- function() { value <- store$read_schedule(); if (is.list(value)) value else list() }
  # `times`: eine oder mehrere Uhrzeiten (bis rc.364 genau eine).
  enable <- function(times, retry_gaps, at) {
    times <- sort(unique(as.character(times)))
    if (!.data_refresh_all_schedule_valid_times_v1(times)) return(list(status = "failed", code = "data_refresh_all_schedule_input_invalid"))
    gaps <- .data_refresh_all_schedule_gaps_of_v1(retry_gaps)
    previous <- saved()
    if (!install("refresh", times, gaps)) {
      store$write_schedule(c(list(enabled = FALSE, time = times[[1L]], times = as.list(times), retry_gaps = gaps, unit = unit), if (is.list(previous$moment)) list(moment = previous$moment)))
      return(list(status = "failed", code = "data_refresh_all_schedule_systemd_failed"))
    }
    store$write_schedule(c(list(enabled = TRUE, time = times[[1L]], times = as.list(times), retry_gaps = gaps, consented_at_utc = at, unit = unit),
                           if (is.list(previous$moment)) list(moment = previous$moment)))
    list(status = "enabled", time = times[[1L]], times = times)
  }
  disable <- function(at) {
    remove("refresh")
    previous <- saved(); times <- .data_refresh_all_schedule_times_of_v1(previous)
    store$write_schedule(c(list(enabled = FALSE, time = times[[1L]], times = as.list(times), retry_gaps = .data_refresh_all_schedule_gaps_of_v1(previous$retry_gaps),
                                disabled_at_utc = at, unit = unit), if (is.list(previous$moment)) list(moment = previous$moment)))
    list(status = "disabled")
  }
  enable_moment <- function(times, at) {
    times <- sort(unique(as.character(times)))
    if (!.data_refresh_all_schedule_valid_times_v1(times)) return(list(status = "failed", code = "data_refresh_all_schedule_input_invalid"))
    previous <- saved()
    if (!install("moment", times, "never")) {
      previous$moment <- list(enabled = FALSE, times = as.list(times), unit = units$moment); store$write_schedule(previous)
      return(list(status = "failed", code = "data_refresh_all_schedule_systemd_failed"))
    }
    previous$moment <- list(enabled = TRUE, times = as.list(times), consented_at_utc = at, unit = units$moment)
    store$write_schedule(previous)
    list(status = "enabled", times = times)
  }
  disable_moment <- function(at) {
    remove("moment")
    previous <- saved(); times <- .data_refresh_all_schedule_times_of_v1(previous$moment)
    previous$moment <- list(enabled = FALSE, times = as.list(times), disabled_at_utc = at, unit = units$moment)
    store$write_schedule(previous)
    list(status = "disabled")
  }
  list(status = status, enable = enable, disable = disable, enable_moment = enable_moment, disable_moment = disable_moment,
       unit = unit, units = units, paths = paths, moment_paths = paths_of("moment"), service_text = service_text, timer_text = timer_text)
}

data_refresh_all_schedule_ui_v1 <- function() portelyra_card(
  "Von selbst aktualisieren",
  copy = "„Alles aktualisieren“ und die Momentaufnahme zu festen Uhrzeiten, ohne dass die App offen sein muss. Vorgabe: aus.",
  note = portelyra_note_v1(title = "So funktionieren die Zeitpläne", id = "data-refresh-schedule", paste(
    "Ein Zeitgeber des Systems (systemd, nur für Ihr Benutzerkonto) startet zu jeder gewählten Uhrzeit denselben Lauf wie der Knopf „Alles aktualisieren“.",
    "Der Zeitplan der Momentaufnahme holt nur aktuelle Kurse und veröffentlicht das Bild von jetzt – schnell, ohne Tageshistorie, Abschluss und Datenbasis.",
    "War der Rechner zu einer Uhrzeit aus oder waren Sie nicht angemeldet, holt der Zeitgeber den Lauf beim nächsten Anmelden nach.",
    "Läuft gerade schon ein Lauf, ein Sammellauf oder eine Wartung (Backup, Upgrade), wartet er bis zu 30 Minuten und startet dann; sonst versucht er es zum nächsten Termin.",
    "Quelllücken der letzten 10 Tage fragt „Alles aktualisieren“ nach Wahl bei jedem Lauf, einmal pro Woche oder nie erneut ab.",
    "Das Ergebnis steht hier und in der Karte „Alles aktualisieren“.")),
  shiny::tags$h4("Alles aktualisieren"),
  shiny::div(class = "pl-field-row",
    shiny::checkboxInput("refresh_schedule_enabled", "Von selbst aktualisieren", FALSE),
    shiny::selectizeInput("refresh_schedule_times", "Uhrzeiten (bis zu 6)", choices = DATA_REFRESH_ALL_SCHEDULE_TIMES_V1, selected = DATA_REFRESH_ALL_SCHEDULE_DEFAULT_V1,
                          multiple = TRUE, options = list(maxItems = DATA_REFRESH_ALL_SCHEDULE_MAX_TIMES_V1), width = "260px"),
    shiny::radioButtons("refresh_schedule_gaps_mode", "Quelllücken der letzten 10 Tage erneut abfragen", choices = DATA_REFRESH_ALL_SCHEDULE_GAPS_V1,
                        selected = "weekly", inline = TRUE)),
  shiny::checkboxInput("refresh_schedule_confirm", paste(
    "Zustimmung: Zu den gewählten Uhrzeiten ruft Portelyra ohne mein Zutun Kurse beim Anbieter ab (nur lesend) und schreibt Bewertungen,",
    "Tageshistorie, Snapshot, den Abschluss, die Momentaufnahme und die Datenbasis – wie „Alles aktualisieren“."), FALSE),
  shiny::actionButton("refresh_schedule_save", "Speichern", class = "btn-primary"),
  shiny::uiOutput("refresh_schedule_state"),
  shiny::tags$h4("Nur die Momentaufnahme"),
  shiny::div(class = "pl-field-row",
    shiny::checkboxInput("moment_schedule_enabled", "Momentaufnahme von selbst", FALSE),
    shiny::selectizeInput("moment_schedule_times", "Uhrzeiten (bis zu 6)", choices = DATA_REFRESH_ALL_SCHEDULE_TIMES_V1, selected = c("10:00", "16:00"),
                          multiple = TRUE, options = list(maxItems = DATA_REFRESH_ALL_SCHEDULE_MAX_TIMES_V1), width = "260px")),
  shiny::checkboxInput("moment_schedule_confirm", paste(
    "Zustimmung: Zu den gewählten Uhrzeiten ruft Portelyra ohne mein Zutun aktuelle Kurse beim Anbieter ab (nur lesend) und veröffentlicht die Momentaufnahme."), FALSE),
  shiny::actionButton("moment_schedule_save", "Speichern", class = "btn-primary"),
  shiny::uiOutput("moment_schedule_state"))

# Ortszeit fuer die Anzeige.
.data_refresh_all_schedule_time_v1 <- function(value) if (is.null(value)) "–" else format(value, "%d.%m.%Y, %H:%M Uhr", tz = "Europe/Berlin")

# Stand eines Zeitplans in einem Satz: an/aus, Uhrzeiten, naechster Lauf und das letzte Ergebnis.
.data_refresh_all_schedule_line_v1 <- function(label, current) {
  times <- paste(unlist(current$times), collapse = ", ")
  state <- if (!isTRUE(current$enabled)) "Aus." else if (isTRUE(current$active)) paste0("An · täglich um ", times, " Uhr · nächster Lauf ", .data_refresh_all_schedule_time_v1(current$next_at), ".")
           else paste0("Eingeschaltet für ", times, " Uhr, aber der Zeitgeber läuft nicht. Einmal aus- und wieder einschalten.")
  last <- current$last
  ended <- if (is.list(last) && is.character(last$finished_at_utc)) suppressWarnings(as.POSIXct(last$finished_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) else NULL
  outcome <- if (is.list(last) && is.list(last$notice)) paste0(" Letzter zeitgesteuerter Lauf: ", .data_refresh_all_schedule_time_v1(ended), " – ", last$notice$title, ".") else ""
  portelyra_status_panel(label, paste0(state, outcome), tone = if (is.list(last) && is.list(last$notice) && !identical(last$notice$tone, "positive")) "warning" else "neutral")
}

data_refresh_all_schedule_server_v1 <- function(input, output, session, schedule, now_utc) {
  view <- shiny::reactiveValues(status = NULL, notice = NULL, moment_notice = NULL, loaded = FALSE)
  load <- function() {
    view$status <- if (is.null(schedule)) NULL else tryCatch(schedule$status(), error = function(error) NULL)
    view$loaded <- TRUE
    current <- view$status
    if (is.list(current)) {
      shiny::updateCheckboxInput(session, "refresh_schedule_enabled", value = isTRUE(current$enabled))
      shiny::updateSelectizeInput(session, "refresh_schedule_times", selected = unlist(current$times))
      shiny::updateRadioButtons(session, "refresh_schedule_gaps_mode", selected = current$retry_gaps)
      if (is.list(current$moment)) {
        shiny::updateCheckboxInput(session, "moment_schedule_enabled", value = isTRUE(current$moment$enabled))
        if (isTRUE(current$moment$enabled)) shiny::updateSelectizeInput(session, "moment_schedule_times", selected = unlist(current$moment$times))
      }
    }
  }
  # Gelesen wird, wenn die Karte sichtbar wird - systemctl kostet einen Prozessstart.
  shiny::observeEvent(input$settings_panel_open, if (isTRUE(input$settings_panel_open) && !isTRUE(view$loaded)) load(), ignoreInit = FALSE)
  failed <- function(result) list(tone = "error", title = "Nicht gespeichert", copy = pl_error_text_v1(result$code))
  unavailable <- list(tone = "error", title = "Nicht verfügbar", copy = "Der Zeitplan lässt sich auf diesem Rechner nicht einrichten.")
  shiny::observeEvent(input$refresh_schedule_save, {
    if (is.null(schedule)) { view$notice <- unavailable; return() }
    wanted <- isTRUE(input$refresh_schedule_enabled)
    if (wanted && !isTRUE(input$refresh_schedule_confirm)) {
      view$notice <- list(tone = "warning", title = "Zustimmung fehlt", copy = "Der Zeitplan ruft Kurse ohne Ihr Zutun ab. Dafür das Häkchen „Zustimmung“ setzen, dann erneut speichern.")
      return()
    }
    if (wanted && !length(input$refresh_schedule_times)) { view$notice <- list(tone = "warning", title = "Uhrzeit fehlt", copy = "Bitte mindestens eine Uhrzeit wählen."); return() }
    result <- tryCatch(if (wanted) schedule$enable(input$refresh_schedule_times, input$refresh_schedule_gaps_mode, now_utc()) else schedule$disable(now_utc()),
                       error = function(error) list(status = "failed", code = conditionMessage(error)))
    shiny::updateCheckboxInput(session, "refresh_schedule_confirm", value = FALSE)
    view$notice <- switch(as.character(result$status),
      enabled = list(tone = "positive", title = "Eingeschaltet", copy = paste0("„Alles aktualisieren“ läuft jetzt täglich um ", paste(result$times, collapse = ", "), " Uhr.")),
      disabled = list(tone = "neutral", title = "Ausgeschaltet", copy = "„Alles aktualisieren“ läuft nicht mehr von selbst; der Knopf bleibt."),
      failed(result))
    load()
  })
  shiny::observeEvent(input$moment_schedule_save, {
    if (is.null(schedule)) { view$moment_notice <- unavailable; return() }
    wanted <- isTRUE(input$moment_schedule_enabled)
    if (wanted && !isTRUE(input$moment_schedule_confirm)) {
      view$moment_notice <- list(tone = "warning", title = "Zustimmung fehlt", copy = "Die Momentaufnahme ruft Kurse ohne Ihr Zutun ab. Dafür das Häkchen „Zustimmung“ setzen, dann erneut speichern.")
      return()
    }
    if (wanted && !length(input$moment_schedule_times)) { view$moment_notice <- list(tone = "warning", title = "Uhrzeit fehlt", copy = "Bitte mindestens eine Uhrzeit wählen."); return() }
    result <- tryCatch(if (wanted) schedule$enable_moment(input$moment_schedule_times, now_utc()) else schedule$disable_moment(now_utc()),
                       error = function(error) list(status = "failed", code = conditionMessage(error)))
    shiny::updateCheckboxInput(session, "moment_schedule_confirm", value = FALSE)
    view$moment_notice <- switch(as.character(result$status),
      enabled = list(tone = "positive", title = "Eingeschaltet", copy = paste0("Die Momentaufnahme läuft jetzt täglich um ", paste(result$times, collapse = ", "), " Uhr.")),
      disabled = list(tone = "neutral", title = "Ausgeschaltet", copy = "Die Momentaufnahme läuft nicht mehr von selbst; „Alles aktualisieren“ veröffentlicht sie weiter."),
      failed(result))
    load()
  })
  panels_for <- function(notice, line) {
    panels <- list()
    if (is.list(notice)) panels[[length(panels) + 1L]] <- portelyra_status_panel(notice$title, notice$copy, tone = notice$tone)
    if (!is.null(line)) panels[[length(panels) + 1L]] <- line
    if (length(panels)) shiny::tagList(panels) else NULL
  }
  output$refresh_schedule_state <- shiny::renderUI({
    current <- view$status
    missing <- if (isTRUE(view$loaded) && !is.list(current))
      portelyra_status_panel("Kein Zeitgeber verfügbar", "Auf diesem Rechner gibt es keinen systemd-Benutzerdienst; die Zeitpläne sind hier nicht möglich.", tone = "warning")
    panels_for(view$notice, if (is.list(current)) .data_refresh_all_schedule_line_v1("Zeitplan", current) else missing)
  })
  output$moment_schedule_state <- shiny::renderUI({
    current <- view$status
    panels_for(view$moment_notice, if (is.list(current) && is.list(current$moment)) .data_refresh_all_schedule_line_v1("Zeitplan der Momentaufnahme", current$moment) else NULL)
  })
  invisible(list(load = load, view = view))
}
