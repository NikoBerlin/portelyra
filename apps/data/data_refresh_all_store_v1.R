# Stand, Sperre und Anhalte-Bitte von „Alles aktualisieren“ im Datenraum (rc.315, #510).
#
# Der Lauf ist ein eigener Prozess (scripts/desktop_refresh_all.R). Die Data-App startet ihn und liest nur diesen Stand; jede
# Data-Seite zeigt so denselben Lauf, auch nach Neuladen, Wechsel in eine andere App oder Schliessen des Tabs.
# - state.json: der Stand der Schrittmaschine (data_refresh_all_engine_v1) samt Laufkennung, Herkunft und Zeitpunkten.
# - lock/: Verzeichnis als Sperre (dir.create ist atomar), darin owner.json mit Prozess und Herzschlag. Ein Lauf, dessen Prozess
#   nicht mehr lebt oder dessen Herzschlag laenger als DATA_REFRESH_ALL_STALE_SECONDS_V1 aussetzt, sperrt nicht mehr. Die Zeit im
#   Ruhezustand zaehlt dabei nicht. Ein noch leeres lock/ gehoert dem, der es gerade angelegt hat; eine verwaiste Sperre
#   raeumt immer nur einer (lock/takeover). Bis dahin hielten zwei gleichzeitig startende Zeitlaeufe beide die Sperre.
# - stop.json: die Bitte anzuhalten, gebunden an die Laufkennung.
# - state-moment.json, last-moment-timer.json: Stand und Ergebnis der Laeufe nur fuer die Momentaufnahme (rc.365, #516). Sie
#   teilen sich die Sperre mit „Alles aktualisieren“, verdecken dessen Stand aber nicht.
# - last-gaps.json: wann Quellluecken zuletzt erneut abgefragt wurden - fuer „einmal pro Woche“ (rc.365, #516).
# - last-run.json, last-moment-run.json: der zuletzt beendete Lauf jeder Art, gleich ob aus der App oder vom Zeitplan - fuer den
#   Block links in allen Apps (#540, rc.366), solange ein neuer Lauf den Stand ueberschreibt.
# Alles nur im Bereich refresh-all-v1 des Datenraums, nie in Speichern der Fachmodule.

DATA_REFRESH_ALL_AREA_V1 <- "refresh-all-v1"

# Inhalt einer Datei vor dem Umbenennen festschreiben (#568): Nach einem Neustart mitten im Lauf war state.json 0 Byte lang,
# weil der Inhalt der Zwischendatei noch nicht auf der Platte lag. R kennt kein fsync; `sync --data <datei>` (coreutils) schreibt genau
# diese Datei fest. Fehlt das Werkzeug oder scheitert es, geht es ohne weiter - die App liest eine leere Datei als „kein Stand“.
data_refresh_all_fsync_v1 <- function(path) {
  tool <- Sys.which("sync")
  if (nzchar(tool)) suppressWarnings(tryCatch(system2(tool, c("--data", shQuote(path)), stdout = FALSE, stderr = FALSE),
                                              error = function(error) NULL))
  invisible(path)
}
# Ein Schritt laeuft am Stueck, der Herzschlag kommt erst danach: Die Tageshistorie braucht bei grossen Bestaenden mehrere Minuten. Bei 180 s
# meldete die App mitten im Lauf "Lauf unterbrochen", und ein zweiter Lauf haette die Sperre uebernehmen koennen.
# Ein beendeter Prozess faellt ohnehin sofort auf (Pruefung der Prozessnummer); die Frist gilt nur fuer einen haengenden.
DATA_REFRESH_ALL_STALE_SECONDS_V1 <- 1200
# So lange gehoert ein lock/ ohne owner.json noch dem, der es gerade anlegt; ebenso lange gilt lock/takeover.
DATA_REFRESH_ALL_CLAIM_SECONDS_V1 <- 60

# Letztes Aufwachen aus dem Ruhezustand in Sekunden seit 1970, NA ohne systemd. Waehrend des Ruhezustands schlaegt kein Herz: Ohne das
# galt ein eingefrorener Lauf beim Aufwachen als verwaist, und der nachgeholte Zeitlauf haette ihm die Sperre genommen. sleep.target
# wird erst Sekunden nach den faelligen Zeitplaenen inaktiv; solange es aktiv ist, zaehlt jetzt als Aufwachen.
data_refresh_all_last_wake_v1 <- function() {
  tool <- Sys.which("systemctl")
  if (!nzchar(tool)) return(NA_real_)
  lines <- tryCatch(suppressWarnings(system2(tool, c("show", "sleep.target", "-p", "ActiveState", "-p", "InactiveEnterTimestamp", "--timestamp=unix"),
                                             stdout = TRUE, stderr = FALSE)), error = function(error) character())
  state <- sub("^ActiveState=", "", grep("^ActiveState=", lines, value = TRUE))
  stamp <- sub("^InactiveEnterTimestamp=@?", "", grep("^InactiveEnterTimestamp=", lines, value = TRUE))
  if (length(state) != 1L) return(NA_real_)
  if (!identical(state, "inactive")) return(as.numeric(Sys.time()))
  if (length(stamp) != 1L || !grepl("^[0-9]+$", stamp)) NA_real_ else as.numeric(stamp)
}

# Quellluecken „einmal pro Woche“ (rc.365, #516): faellig, wenn die letzte Abfrage mehr als sechseinhalb Tage zurueckliegt - so
# trifft ein taeglicher Lauf zur selben Uhrzeit sicher jeden siebten Tag, auch wenn er sich um Minuten verschiebt.
DATA_REFRESH_ALL_GAPS_EVERY_SECONDS_V1 <- 6.5 * 86400
data_refresh_all_gaps_due_v1 <- function(last_utc, now = Sys.time()) {
  if (!is.character(last_utc) || length(last_utc) != 1L || is.na(last_utc)) return(TRUE)
  last <- suppressWarnings(as.POSIXct(last_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  is.na(last) || as.numeric(difftime(now, last, units = "secs")) >= DATA_REFRESH_ALL_GAPS_EVERY_SECONDS_V1
}

data_refresh_all_store_file_v1 <- function(name, kind = "refresh") {
  if (!isTRUE(kind %in% c("refresh", "moment"))) stop("data_refresh_all_store_invalid", call. = FALSE)
  if (identical(kind, "moment")) paste0(switch(as.character(name)[1L], state = "state-moment", `last-run` = "last-moment-run", "last-moment-timer"), ".json")
  else paste0(name, ".json")
}

# Wer die Sperre haelt, in Worten (rc.365, #516) - fuer die Hinweise der Data-App.
data_refresh_all_holder_text_v1 <- function(holder) {
  if (!is.list(holder)) return(NULL)
  what <- switch(as.character(holder$origin), app = "„Alles aktualisieren“", timer = "der zeitgesteuerte Lauf", timer_moment = "die zeitgesteuerte Momentaufnahme",
    app_sweep = "der Sammellauf im Reiter Marktdaten", data_basis_names = "das Nachtragen der Namen in der Datenbasis", maintenance = "eine Wartung (Backup oder Upgrade)",
    "ein Lauf")
  since <- suppressWarnings(as.POSIXct(as.character(holder$started_at_utc), format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  paste0(what, if (length(since) == 1L && !is.na(since)) paste0(" seit ", format(since, "%H:%M", tz = ""), " Uhr") else "")
}

data_refresh_all_store_v1 <- function(data_space, last_wake = data_refresh_all_last_wake_v1) {
  if (!is.character(data_space) || length(data_space) != 1L || !dir.exists(data_space)) stop("data_refresh_all_store_invalid", call. = FALSE)
  area <- file.path(data_space, DATA_REFRESH_ALL_AREA_V1)
  lock <- file.path(area, "lock")
  ensure <- function() {
    if (!dir.exists(area)) dir.create(area, mode = "0700")
    if (nzchar(Sys.readlink(area))) stop("data_refresh_all_store_invalid", call. = FALSE)
    invisible(area)
  }
  utc <- function(time = Sys.time()) format(time, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  write_json <- function(path, value) {
    ensure()
    temp <- paste0(path, ".tmp-", Sys.getpid())
    old <- Sys.umask("0077"); on.exit(Sys.umask(old), add = TRUE)
    writeLines(as.character(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", na = "null", digits = NA, pretty = FALSE)), temp, useBytes = TRUE)
    data_refresh_all_fsync_v1(temp)
    if (!file.rename(temp, path)) { unlink(temp); stop("data_refresh_all_store_write_failed", call. = FALSE) }
    invisible(path)
  }
  read_json <- function(path) {
    if (!file.exists(path) || nzchar(Sys.readlink(path)) || isTRUE(file.info(path)$size > 5000000)) return(NULL)
    tryCatch(jsonlite::fromJSON(paste(readLines(path, warn = FALSE, encoding = "UTF-8"), collapse = ""), simplifyVector = FALSE),
             error = function(error) NULL)
  }
  alive <- function(pid) {
    pid <- suppressWarnings(as.integer(pid))
    length(pid) == 1L && !is.na(pid) && pid > 0L && isTRUE(tryCatch(tools::pskill(pid, 0L), error = function(error) FALSE))
  }
  owner <- function() read_json(file.path(lock, "owner.json"))
  # Wer sperrt gerade? NULL, wenn niemand - oder nur noch ein verwaister Eintrag.
  holder <- function() {
    if (!dir.exists(lock)) return(NULL)
    value <- owner()
    beat <- if (is.list(value)) suppressWarnings(as.POSIXct(value$heartbeat_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) else NA
    if (!is.list(value) || !alive(value$pid) || is.na(beat)) return(NULL)
    age <- as.numeric(difftime(Sys.time(), beat, units = "secs"))
    if (age > DATA_REFRESH_ALL_STALE_SECONDS_V1) {
      wake <- last_wake()
      if (!is.na(wake)) age <- min(age, as.numeric(Sys.time()) - wake)
    }
    if (age > DATA_REFRESH_ALL_STALE_SECONDS_V1) NULL else value
  }
  recent <- function(path) {
    age <- as.numeric(difftime(Sys.time(), file.mtime(path), units = "secs"))
    !is.na(age) && age < DATA_REFRESH_ALL_CLAIM_SECONDS_V1
  }
  # Eine verwaiste Sperre raeumt nur, wer lock/takeover anlegen konnte, und erst nach einem zweiten Blick. Der Merker liegt in lock/, weil
  # Backups diesen Ordner auslassen (_run_lock); neben lock/ fiele er zwischen zwei Lesedurchgaengen als geaenderte Quelle auf.
  clear_orphan <- function(seen) {
    guard <- file.path(lock, "takeover")
    if (!dir.create(guard, showWarnings = FALSE, mode = "0700")) {
      if (dir.exists(guard) && !recent(guard)) unlink(guard, recursive = TRUE)
      return(FALSE)
    }
    # Steht jetzt etwas anderes drin, hat ein anderer die Sperre inzwischen neu angelegt. Ein leeres lock/ bekommt eine Sekunde: Wer es
    # gerade angelegt hat, traegt sich in dieser Zeit ein.
    if (is.null(seen)) Sys.sleep(1)
    if (!identical(owner(), seen) || !is.null(holder())) { unlink(guard, recursive = TRUE); return(FALSE) }
    unlink(lock, recursive = TRUE)
    TRUE
  }
  acquire <- function(run_id, origin) {
    ensure()
    if (!dir.create(lock, showWarnings = FALSE, mode = "0700")) {
      if (!is.null(holder())) return(FALSE)
      if (!file.exists(file.path(lock, "owner.json")) && recent(lock)) return(FALSE)   # wird gerade angelegt
      # Verwaist: Prozess beendet oder Herzschlag ausgesetzt. Einmal raeumen und erneut versuchen.
      if (!clear_orphan(owner()) || !dir.create(lock, showWarnings = FALSE, mode = "0700")) return(FALSE)
    }
    claimed <- tryCatch({
      suppressWarnings(write_json(file.path(lock, "owner.json"), list(run_id = run_id, origin = origin, pid = Sys.getpid(),
                                                                      started_at_utc = utc(), heartbeat_at_utc = utc())))
      TRUE
    }, error = function(error) if (dir.exists(lock)) stop(error) else FALSE)   # die Sperre ist weg: ein anderer hat sie, kein Abbruch
    claimed && identical(owner()$run_id, run_id)
  }
  heartbeat <- function(run_id) {
    value <- owner()
    if (is.list(value) && identical(value$run_id, run_id) && identical(as.integer(value$pid), Sys.getpid())) {
      value$heartbeat_at_utc <- utc(); write_json(file.path(lock, "owner.json"), value)
    }
    invisible(NULL)
  }
  # Herzschlag durch einen Begleitprozess (rc.410): Wartung (Backup, Upgrade) steht lange in einem Aufruf des Workers und kann den
  # Herzschlag nicht selbst erneuern. Der Begleiter erneuert ihn fuer genau diesen Lauf; ob der sperrende Prozess noch lebt, prueft
  # holder() weiter an dessen Nummer.
  keep <- function(run_id) {
    value <- owner()
    if (is.list(value) && identical(value$run_id, run_id)) { value$heartbeat_at_utc <- utc(); write_json(file.path(lock, "owner.json"), value) }
    invisible(NULL)
  }
  release <- function(run_id) {
    value <- owner()
    if (is.list(value) && identical(value$run_id, run_id)) unlink(lock, recursive = TRUE)
    unlink(file.path(area, "stop.json"))
    invisible(NULL)
  }
  list(
    area = area,
    utc = utc,
    holder = holder,
    acquire = acquire,
    heartbeat = heartbeat,
    keep = keep,
    release = release,
    # `kind`: "refresh" fuer „Alles aktualisieren“, "moment" fuer Laeufe nur der Momentaufnahme (rc.365).
    write_state = function(value, kind = "refresh") write_json(file.path(area, data_refresh_all_store_file_v1("state", kind)), value),
    # Ergebnis des letzten zeitgesteuerten Laufs (rc.316) und die Einstellung des Zeitplans.
    write_last_timer = function(value, kind = "refresh") write_json(file.path(area, data_refresh_all_store_file_v1("last-timer", kind)), value),
    read_last_timer = function(kind = "refresh") read_json(file.path(area, data_refresh_all_store_file_v1("last-timer", kind))),
    # Der zuletzt beendete Lauf jeder Art (#540).
    write_last_run = function(value, kind = "refresh") write_json(file.path(area, data_refresh_all_store_file_v1("last-run", kind)), value),
    read_last_run = function(kind = "refresh") read_json(file.path(area, data_refresh_all_store_file_v1("last-run", kind))),
    write_schedule = function(value) write_json(file.path(area, "schedule.json"), value),
    read_schedule = function() read_json(file.path(area, "schedule.json")),
    read_state = function(kind = "refresh") read_json(file.path(area, data_refresh_all_store_file_v1("state", kind))),
    write_gaps_done = function(at = utc()) write_json(file.path(area, "last-gaps.json"), list(retried_at_utc = at)),
    read_gaps_done = function() { value <- read_json(file.path(area, "last-gaps.json")); if (is.list(value) && is.character(value$retried_at_utc)) value$retried_at_utc else NULL },
    request_stop = function(run_id) write_json(file.path(area, "stop.json"), list(run_id = run_id, requested_at_utc = utc())),
    stop_requested = function(run_id) { value <- read_json(file.path(area, "stop.json")); is.list(value) && identical(value$run_id, run_id) }
  )
}

# Startet den Lauf als eigenen Prozess, abgekoppelt von der Data-App (setsid, wo vorhanden): Er laeuft weiter, wenn die Seite
# geschlossen oder die App beendet wird. Gestartet gilt er, sobald seine Statusdatei mit der Laufkennung da ist.
data_refresh_all_spawn_v1 <- function(project_root, runtime, store, retry_gaps, origin = "app", wait_seconds = 20) {
  script <- file.path(project_root, "scripts", "desktop_refresh_all.R")
  rscript <- file.path(R.home("bin"), "Rscript")
  if (!file.exists(script) || !file.exists(rscript) || is.null(store) || !is.character(runtime$home)) return(list(status = "failed", code = "refresh_all_runner_missing"))
  run_id <- paste0("run_", format(Sys.time(), "%Y%m%d%H%M%S", tz = "UTC"), substr(digest::digest(paste(Sys.getpid(), stats::runif(1L), Sys.time())), 1L, 8L))
  if (!dir.exists(store$area)) dir.create(store$area, mode = "0700")
  log <- file.path(store$area, "runner.log")
  args <- c(script, "--home", runtime$home, "--run-id", run_id, "--origin", origin, "--retry-gaps", if (isTRUE(retry_gaps)) "yes" else "no",
            "--confirm", "RUN_REFRESH_ALL")
  setsid <- Sys.which("setsid")
  command <- if (nzchar(setsid)) unname(setsid) else rscript
  # Nur fuer den Eigentuemer lesbar: Das Backup nimmt im Datenraum keine Datei mit offeneren Rechten an (so
  # brach das Backup vor rc.316 an runner.log mit 0664 ab).
  old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
  system2(command, shQuote(if (nzchar(setsid)) c(rscript, args) else args), wait = FALSE, stdout = log, stderr = log,
          env = "PYTHONDONTWRITEBYTECODE=1")
  deadline <- Sys.time() + wait_seconds
  while (Sys.time() < deadline) {
    state <- store$read_state()
    if (is.list(state) && identical(state$run_id, run_id)) return(list(status = "started", run_id = run_id))
    Sys.sleep(0.25)
  }
  list(status = "failed", code = "refresh_all_start_timeout")
}
