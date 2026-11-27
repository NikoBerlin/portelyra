# Backups ohne Kommandozeile (#559, rc.407): wohin sie gehen, welcher Auftrag laeuft, und wie die Data-App ihn startet. Gemeinsam fuer
# das Startskript (Befehl backup-live) und die Karte „Backups“ in Data. Braucht desktop_protection_cli_v1 (desktop_protection_v1.R).

# Der Backup-Ordner von Portelyra: mit Passwortschutz der eingehaengte, verschluesselte (gesperrt: kein Ziel); sonst
# $XDG_STATE_HOME/portelyra/backups - derselbe Ordner wie bei den Rollouts und dem Notfallweg (#535). Er gehoert allen Homes eines
# Benutzerkontos; die Liste zeigt deshalb, welches Backup zu diesem Datenraum gehoert.
desktop_backups_root_v1 <- function(project_root, home, runner = NULL) {
  status <- tryCatch(desktop_protection_cli_v1(project_root, home, "status", runner = runner), error = function(error) NULL)
  if (!is.list(status) || !identical(status$status, "completed") || !is.list(status$result))
    return(list(status = "blocked", code = "desktop_backups_root_unavailable"))
  if (isTRUE(status$result$enabled)) {
    root <- status$result$backups_root
    if (!is.character(root) || length(root) != 1L || !nzchar(root)) return(list(status = "blocked", code = "desktop_protection_locked"))
    return(list(status = "ready", root = root, protected = TRUE))
  }
  state <- Sys.getenv("XDG_STATE_HOME", unset = "")
  if (!nzchar(state)) state <- file.path(path.expand("~"), ".local", "state")
  list(status = "ready", root = file.path(state, "portelyra", "backups"), protected = FALSE)
}

# Der laufende oder letzte Auftrag „Backup anlegen“: <home>/backup-job.json (0600). Er liegt bewusst neben dem Datenraum und nicht
# darin - sonst saehe das Backup seinen eigenen Zustand als unruhigen Stand.
desktop_backups_job_path_v1 <- function(home) file.path(home, "backup-job.json")
desktop_backups_job_read_v1 <- function(home) {
  path <- desktop_backups_job_path_v1(home)
  if (!file.exists(path) || nzchar(Sys.readlink(path))) return(NULL)
  value <- tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(value) || !is.character(value$status)) return(NULL)
  # Ein Auftrag „running“, dessen Prozess nicht mehr lebt, ist abgebrochen (etwa Rechner neu gestartet). Verglichen wird auch die
  # Startzeit des Prozesses (rc.410): Nach einem Neustart kann dieselbe Nummer einem fremden Prozess gehoeren - der Auftrag haette dann
  # dauerhaft „läuft“ gezeigt und jedes neue Backup gesperrt.
  if (identical(value$status, "running") && !desktop_backups_pid_alive_v1(suppressWarnings(as.integer(value$pid)), value$process_start))
    value <- c(value[setdiff(names(value), c("status", "code"))], list(status = "failed", code = "desktop_backups_job_interrupted"))
  value
}
# Zustand und Startzeit eines Prozesses aus /proc/<pid>/stat (der Name in Klammern kann Leerzeichen tragen: ab der letzten „) “ lesen).
desktop_backups_process_v1 <- function(pid) {
  if (!is.integer(pid) || length(pid) != 1L || is.na(pid) || pid < 1L) return(NULL)
  line <- suppressWarnings(tryCatch(readLines(file.path("/proc", pid, "stat"), warn = FALSE, n = 1L), error = function(error) character()))
  if (length(line) != 1L) return(NULL)
  positions <- gregexpr(") ", line, fixed = TRUE)[[1L]]; positions <- positions[positions > 0L]
  if (!length(positions)) return(NULL)
  fields <- strsplit(substring(line, positions[[length(positions)]] + 2L), " ", fixed = TRUE)[[1L]]
  if (length(fields) < 20L) return(NULL)
  list(state = fields[[1L]], start = fields[[20L]])
}
desktop_backups_pid_alive_v1 <- function(pid, process_start = NULL) {
  process <- desktop_backups_process_v1(pid)
  if (is.null(process) || identical(process$state, "Z")) return(FALSE)
  # Ohne vermerkte Startzeit (Auftrag aus rc.407-409) zaehlt nur, dass der Prozess lebt.
  !(is.character(process_start) && length(process_start) == 1L) || identical(process$start, process_start)
}
desktop_backups_job_write_v1 <- function(home, value) {
  path <- desktop_backups_job_path_v1(home)
  old <- Sys.umask("0077"); on.exit(Sys.umask(old), add = TRUE)
  temp <- paste0(path, ".tmp-", Sys.getpid())
  writeLines(as.character(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null")), temp, useBytes = TRUE)
  Sys.chmod(temp, "0600")
  if (!file.rename(temp, path)) { unlink(temp); stop("desktop_backups_job_write_failed", call. = FALSE) }
  invisible(value)
}

# Die Umgebung des Startwegs. system2 setzt `env` unveraendert vor den Befehl: Ohne Anfuehrung zerlegte die Shell einen Home-Pfad mit
# Leerzeichen, und „Backup anlegen“ waere nie gestartet (rc.410, Review 13.11.2026).
desktop_backups_spawn_env_v1 <- function(home) c("PYTHONDONTWRITEBYTECODE=1", paste0("PORTELYRA_DESKTOP_HOME=", shQuote(home)))

# Startet „Backup anlegen“ als eigenen Prozess (wie „Alles aktualisieren“, rc.315): Er ueberlebt Neuladen und Wechsel der App. Zurueck
# kommt "started" erst, wenn der Prozess seinen Auftrag geschrieben hat.
desktop_backups_spawn_v1 <- function(project_root, home, wait_seconds = 20) {
  script <- file.path(project_root, "scripts", "portelyra_desktop.R")
  rscript <- file.path(R.home("bin"), "Rscript")
  if (!file.exists(script) || !file.exists(rscript)) return(list(status = "failed", code = "desktop_backups_runner_missing"))
  running <- desktop_backups_job_read_v1(home)
  if (is.list(running) && identical(running$status, "running")) return(list(status = "failed", code = "desktop_backups_job_running"))
  before <- if (is.list(running)) running$started_at_utc else NULL
  log <- file.path(home, "backup-job.log")
  setsid <- Sys.which("setsid")
  command <- if (nzchar(setsid)) unname(setsid) else rscript
  args <- c(script, "backup-live", "--confirm", "CREATE_OWNER_BACKUP")
  old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
  system2(command, shQuote(if (nzchar(setsid)) c(rscript, args) else args), wait = FALSE, stdout = log, stderr = log,
          env = desktop_backups_spawn_env_v1(home))
  deadline <- Sys.time() + wait_seconds
  while (Sys.time() < deadline) {
    job <- desktop_backups_job_read_v1(home)
    if (is.list(job) && !identical(job$started_at_utc, before)) return(list(status = "started", job = job))
    Sys.sleep(0.25)
  }
  list(status = "failed", code = "desktop_backups_start_timeout")
}

# Gruende in Worten (#559): was ein Code fuer den Nutzer heisst und was er tun kann. relative_path nennt bei einem unlesbaren Eintrag
# (#568) genau diesen, relativ zum Datenraum - siehe „Grund immer genau zeigen“.
desktop_backups_reason_v1 <- function(code, relative_path = NULL) {
  text <- if (is.null(code) || length(code) != 1L || is.na(code)) "" else as.character(code)
  if (identical(text, "desktop_release_source_unreadable")) {
    shown <- if (is.character(relative_path) && length(relative_path) == 1L && !is.na(relative_path) && nzchar(relative_path))
      paste0(" „", relative_path, "“") else ""
    return(paste0("Ein Eintrag im Datenraum lässt sich nicht lesen", shown, ". Das kommt meist von einem Neustart mitten in einem Lauf. ",
                  "Solange er da ist, entsteht kein Backup. Was zu tun ist, steht im Handbuch „Backups“ unter „Unlesbarer Eintrag“."))
  }
  switch(text,
    desktop_product_refresh_running = "Gerade läuft „Alles aktualisieren“, ein Zeitlauf oder ein Sammellauf. Ihn abwarten, dann erneut.",
    desktop_release_source_unsettled = "Gerade wird geschrieben (etwa eine Buchung oder eine Vorschau). In einer Minute erneut versuchen.",
    desktop_release_session_invalid = "Portelyra läuft nicht in dieser Sitzung. Bitte Portelyra neu starten und erneut versuchen.",
    desktop_protection_locked = "Der verschlüsselte Backup-Ordner ist gesperrt. Portelyra entsperren und erneut versuchen.",
    desktop_backups_job_interrupted = "Das Backup wurde unterbrochen (etwa durch einen Neustart). Es ist unvollständig und wird nicht verwendet.",
    desktop_backups_job_running = "Ein Backup läuft bereits.",
    desktop_backups_root_unavailable = "Der Backup-Ordner ist nicht lesbar.",
    desktop_release_target_exists = "Ein Backup mit diesem Namen gibt es schon. In einer Minute erneut versuchen.",
    if (nzchar(text)) pl_error_text_v1(text) else "")
}
