# Demo-Home im Release (#487, rc.412): Orte, Marke, Schutzregeln und Aufbau des Demo-Portfolios.
#
# Festlegungen (13.11.2026): Das Demo liegt in einem eigenen Home - eigener Ordner, eigene Ports, eigener Zustandsordner -
# und beruehrt den eigenen Bestand nie. Echte Assets, erfundene Mengen; ohne Netz bewertet mit den Kursen der Buchungen (Umfang ohne
# Kursabruf, #567), Yahoo laesst sich im Demo zuschalten. Kein Binaer-Backup im Release: Das Demo entsteht beim ersten Aufruf offline aus
# Textdateien (apps/demo/content) ueber dieselben Kernwege wie Einrichtung und Data-App (scripts/desktop_demo.R).
#
# Der Zustandsordner dient dem Demo als eigenes XDG_STATE_HOME: Backup-Ordner und verschluesselter Backup-Ordner liegen fest unter
# $XDG_STATE_HOME/portelyra und gehoeren allen Homes eines Benutzerkontos - ohne eigenen Zustandsordner teilte das Demo sie mit dem
# eigenen Bestand. Eine Marke im Zustandsordner sagt, dass dieses Home ein Demo ist und woher es stammt; ohne Marke wird ein
# vorhandener Ordner nie angefasst. Vertrag und Orte sind dieselben wie im Entwicklerwerkzeug dev/demo_home.

DESKTOP_DEMO_HOME_CONTRACT_V1 <- "portelyra_demo_home_v1"
DESKTOP_DEMO_HOME_MARKER_V1 <- "portelyra-demo.json"
DESKTOP_DEMO_HOME_CONTENT_V1 <- "demo-portfolio-v1"
# Eigene Ports, damit das Demo neben dem eigenen Portelyra laufen kann (dessen Vorgabe: 3838 bis 3841).
DESKTOP_DEMO_HOME_PORT_V1 <- 4838L
# Kenntnisnahme der Hinweise und Bedingungen des Kursanbieters fuer `demo --prices yahoo` (rc.414), wie die Frage „Kurse“ der Einrichtung.
DESKTOP_DEMO_HOME_TERMS_CONFIRM_V1 <- "ACKNOWLEDGE_PROVIDER_TERMS"
DESKTOP_DEMO_HOME_REASONS_V1 <- c(
  desktop_demo_home_path_invalid = "Der Ort des Demos ist nicht zulässig: Der Ordner muss „demo“ im Namen tragen und darf nicht der eigene Bestand sein.",
  desktop_demo_home_state_invalid = "Der Zustandsordner des Demos ist nicht zulässig: Er muss „demo“ im Namen tragen und darf nicht der allgemeine sein.",
  desktop_demo_home_not_empty = "Am Ort des Demos liegt schon ein Ordner, der nicht als Demo gekennzeichnet ist. Er bleibt unberührt.",
  desktop_demo_home_runner_missing = "Das Demo lässt sich aus diesem Programmstand nicht aufbauen (Startdateien fehlen).",
  desktop_demo_home_install_failed = "Das Demo ließ sich nicht installieren.",
  desktop_demo_home_build_failed = "Der Aufbau des Demos ist nicht durchgelaufen. Ein erneuter Aufruf setzt ihn fort.",
  desktop_demo_home_start_timeout = "Das Demo ist nicht angelaufen.",
  desktop_demo_home_terms_required = "Für Kurse von Yahoo bitte die Hinweise und Bedingungen des Anbieters zur Kenntnis nehmen.",
  desktop_demo_home_market_failed = "Die Kurse von Yahoo ließen sich nicht einschalten. Das Demo zeigt die Kurse der Buchungen.",
  desktop_product_session_conflict = "Das Demo läuft schon.")

desktop_demo_home_reason_v1 <- function(code) {
  text <- if (is.character(code) && length(code) == 1L && !is.na(code)) code else ""
  if (text %in% names(DESKTOP_DEMO_HOME_REASONS_V1)) DESKTOP_DEMO_HOME_REASONS_V1[[text]] else pl_error_text_v1(text)
}

# Orte: Home ~/.local/share/portelyra-demo, Zustand ~/.local/state/portelyra-demo. PORTELYRA_DEMO_HOME und PORTELYRA_DEMO_STATE setzen
# andere Orte (Tests, ein zweites Demo); die Schutzregeln gelten auch dort.
desktop_demo_home_paths_v1 <- function() {
  base <- path.expand(Sys.getenv("HOME", unset = ""))
  home <- Sys.getenv("PORTELYRA_DEMO_HOME", unset = "")
  state <- Sys.getenv("PORTELYRA_DEMO_STATE", unset = "")
  if (!nzchar(home)) home <- if (nzchar(base)) file.path(base, ".local", "share", "portelyra-demo") else ""
  if (!nzchar(state)) state <- if (nzchar(base)) file.path(base, ".local", "state", "portelyra-demo") else ""
  list(home = sub("/+$", "", path.expand(home)), state = sub("/+$", "", path.expand(state)))
}

.desktop_demo_home_resolved_v1 <- function(path) normalizePath(path, winslash = "/", mustWork = FALSE)
.desktop_demo_home_within_v1 <- function(inner, outer) identical(inner, outer) || startsWith(inner, paste0(outer, "/"))

# Nie der eigene Bestand: NULL, wenn die Orte zulaessig sind, sonst der Grund. `own_home` ist das Home des eigenen Portelyra.
desktop_demo_home_guard_v1 <- function(paths, own_home = NULL) {
  plain <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && startsWith(value, "/") && !grepl("[[:cntrl:]]", value)
  if (!is.list(paths) || !plain(paths$home) || !plain(paths$state)) return("desktop_demo_home_path_invalid")
  home <- .desktop_demo_home_resolved_v1(paths$home); state <- .desktop_demo_home_resolved_v1(paths$state)
  if (basename(home) %in% c("portelyra", "portelyra-primary") || !grepl("demo", basename(home), fixed = TRUE)) return("desktop_demo_home_path_invalid")
  if (plain(own_home)) {
    own <- .desktop_demo_home_resolved_v1(own_home)
    if (.desktop_demo_home_within_v1(home, own) || .desktop_demo_home_within_v1(own, home)) return("desktop_demo_home_path_invalid")
  }
  general <- Sys.getenv("XDG_STATE_HOME", unset = "")
  general <- c(if (nzchar(general)) .desktop_demo_home_resolved_v1(path.expand(general)),
               .desktop_demo_home_resolved_v1(file.path(path.expand("~"), ".local", "state")))
  if (state %in% general || !grepl("demo", basename(state), fixed = TRUE) || .desktop_demo_home_within_v1(state, home) ||
      .desktop_demo_home_within_v1(home, state)) return("desktop_demo_home_state_invalid")
  NULL
}

desktop_demo_home_marker_read_v1 <- function(state) {
  path <- file.path(state, DESKTOP_DEMO_HOME_MARKER_V1)
  if (!file.exists(path) || nzchar(Sys.readlink(path))) return(NULL)
  value <- tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(error) NULL)
  if (is.list(value) && identical(value$contract_version, DESKTOP_DEMO_HOME_CONTRACT_V1) && is.character(value$home)) value else NULL
}
desktop_demo_home_marker_write_v1 <- function(state, value) {
  path <- file.path(state, DESKTOP_DEMO_HOME_MARKER_V1)
  staged <- paste0(path, ".neu")
  old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
  writeLines(as.character(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null")), staged, useBytes = TRUE)
  Sys.chmod(staged, "0600", use_umask = FALSE)
  if (!file.rename(staged, path)) stop("desktop_demo_home_build_failed", call. = FALSE)
  invisible(value)
}
.desktop_demo_home_stamp_v1 <- function() format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")

# Zustand des Demos an seinen Orten:
#   absent    nichts da - der erste Aufruf baut es auf;
#   building  ein Aufbau aus dem Release ist begonnen und nicht fertig - der naechste Aufruf setzt ihn fort;
#   ready     fertig: starten;
#   foreign   am Ort liegt etwas, das nicht als dieses Demo gekennzeichnet ist - nie anfassen.
# Ein Demo-Home ohne Herkunft "release" stammt aus dev/demo_home (mit Kursabruf aufgebaut): Es wird gestartet, aber nie umgebaut.
desktop_demo_home_status_v1 <- function(paths) {
  marker <- desktop_demo_home_marker_read_v1(paths$state)
  initialized <- file.exists(file.path(paths$home, "desktop-runtime.json"))
  occupied <- dir.exists(paths$home) && length(list.files(paths$home, all.files = TRUE, no.. = TRUE)) > 0L
  if (is.null(marker)) return(list(status = if (occupied) "foreign" else "absent", origin = NULL))
  if (!identical(marker$home, paths$home)) return(list(status = "foreign", origin = NULL))
  if (!identical(marker$origin, "release")) return(list(status = if (initialized) "ready" else "foreign", origin = "dev"))
  list(status = if (identical(marker$status, "ready") && initialized) "ready" else "building", origin = "release")
}

# Umgebung der Prozesse am Demo-Home. system2 setzt `env` als Zuweisungen vor den Befehl einer Shell-Zeile: Werte mit Leerzeichen
# brauchen deshalb Anfuehrungszeichen (wie desktop_backups_spawn_env_v1).
desktop_demo_home_env_v1 <- function(paths) c(
  paste0("PORTELYRA_DESKTOP_HOME=", shQuote(paths$home)), paste0("XDG_STATE_HOME=", shQuote(paths$state)), "PYTHONDONTWRITEBYTECODE=1")

.desktop_demo_home_json_lines_v1 <- function(lines) {
  values <- lapply(lines, function(line) tryCatch(jsonlite::fromJSON(line, simplifyVector = FALSE), error = function(error) NULL))
  Filter(function(value) is.list(value) && !is.null(names(value)), values)
}

# Fuehrt ein Skript am Demo-Home aus und reicht seine Schritte laufend durch (rc.413): Der Dialog zeigt sie, waehrend gebaut wird.
# Deshalb Zeile fuer Zeile aus einer Pipe gelesen statt am Ende gesammelt - der laengste Schritt dauert rund zwei Minuten.
.desktop_demo_home_stream_v1 <- function(rscript, script, env, say) {
  connection <- pipe(paste(c(env, shQuote(c(rscript, "--vanilla", script)), "2>/dev/null"), collapse = " "), open = "r")
  values <- list(); code <- NULL
  tryCatch(repeat {
    line <- readLines(connection, n = 1L, warn = FALSE)
    if (!length(line)) break
    value <- .desktop_demo_home_json_lines_v1(line)
    if (length(value) && is.character(value[[1L]]$step)) { values[[length(values) + 1L]] <- value[[1L]]; say(value[[1L]]) }
  }, finally = { code <- close(connection) })
  list(code = if (is.null(code)) 0L else as.integer(code), values = values)
}

# Baut das Demo auf oder setzt einen begonnenen Aufbau fort: Ordner, Marke, Installation, Einrichtung, Katalog, Buchungen und einmal
# „Alles aktualisieren“ - offline. `say(step)` bekommt je Schritt eine Liste (step, status, ...). Liefert list(status = "ready") oder
# list(status = "failed", code). Die Schutzregeln (desktop_demo_home_guard_v1) prueft der Aufrufer vorher.
# Beispielbeleg fuer die Uebung in "Erste Schritte" (#488, rc.436): ein erfundener Trade-Republic-Export, in den Ordner des Demos gelegt -
# bei jedem Aufbau und Start, falls er fehlt. Ein vorhandener bleibt, wie er ist.
DESKTOP_DEMO_HOME_EXAMPLE_V1 <- "trade-republic-transactions.csv"
desktop_demo_home_example_v1 <- function(project_root, paths) {
  source <- file.path(project_root, "apps", "demo", "content", "beispielbeleg", DESKTOP_DEMO_HOME_EXAMPLE_V1)
  folder <- file.path(paths$home, "beispielbeleg"); target <- file.path(folder, DESKTOP_DEMO_HOME_EXAMPLE_V1)
  if (!file.exists(source) || !dir.exists(paths$home) || file.exists(target)) return(invisible(file.exists(target)))
  if (!dir.exists(folder)) dir.create(folder, mode = "0700")
  ok <- file.copy(source, target, overwrite = FALSE)
  if (isTRUE(ok)) Sys.chmod(target, "0600", use_umask = FALSE)
  invisible(isTRUE(ok))
}

desktop_demo_home_build_v1 <- function(project_root, paths, say = function(step) invisible(NULL)) {
  rscript <- file.path(R.home("bin"), "Rscript")
  launcher <- file.path(project_root, "scripts", "portelyra_desktop.R")
  builder <- file.path(project_root, "scripts", "desktop_demo.R")
  if (!all(file.exists(c(rscript, launcher, builder)))) return(list(status = "failed", code = "desktop_demo_home_runner_missing"))
  state <- desktop_demo_home_status_v1(paths)
  if (identical(state$status, "foreign")) return(list(status = "failed", code = "desktop_demo_home_not_empty"))
  if (identical(state$status, "ready")) { desktop_demo_home_example_v1(project_root, paths); return(list(status = "ready")) }
  for (path in c(paths$home, paths$state)) {
    if (!dir.exists(path)) dir.create(path, recursive = TRUE, mode = "0700")
    Sys.chmod(path, "0700", use_umask = FALSE)
  }
  marker <- desktop_demo_home_marker_read_v1(paths$state)
  if (is.null(marker)) marker <- desktop_demo_home_marker_write_v1(paths$state, list(
    contract_version = DESKTOP_DEMO_HOME_CONTRACT_V1, home = paths$home, created_at_utc = .desktop_demo_home_stamp_v1(),
    origin = "release", content = DESKTOP_DEMO_HOME_CONTENT_V1, status = "building"))
  env <- desktop_demo_home_env_v1(paths)
  run <- function(args) {
    lines <- suppressWarnings(system2(rscript, shQuote(c("--vanilla", args)), stdout = TRUE, stderr = FALSE, env = env))
    code <- attr(lines, "status")
    list(code = if (is.null(code)) 0L else as.integer(code), values = .desktop_demo_home_json_lines_v1(as.character(lines)))
  }
  last <- function(result) if (length(result$values)) result$values[[length(result$values)]] else list()
  if (!file.exists(file.path(paths$home, "desktop-runtime.json"))) {
    if (!dir.exists(file.path(paths$home, "library"))) dir.create(file.path(paths$home, "library"), mode = "0700")
    for (command in list(c("install", "--confirm", "INSTALL_LOCAL_RUNTIME"),
                         c("initialize", "--label", "Demo", "--confirm", "INITIALIZE_LOCAL_DESKTOP"))) {
      result <- run(c(launcher, command))
      value <- last(result)
      say(list(step = command[[1L]], status = value$status, code = value$code))
      if (result$code != 0L || !isTRUE(value$status %in% c("installed", "initialized")))
        return(list(status = "failed", code = "desktop_demo_home_install_failed", detail = value$code))
    }
  }
  result <- .desktop_demo_home_stream_v1(rscript, builder, env, say)
  steps <- result$values
  done <- length(steps) && identical(steps[[length(steps)]]$step, "demo") && identical(steps[[length(steps)]]$status, "ready")
  if (result$code != 0L || !done) {
    failed <- Filter(function(value) identical(value$status, "failed"), steps)
    return(list(status = "failed", code = "desktop_demo_home_build_failed", detail = if (length(failed)) failed[[1L]]$code else NULL))
  }
  marker$status <- "ready"; marker$ready_at_utc <- .desktop_demo_home_stamp_v1()
  desktop_demo_home_marker_write_v1(paths$state, marker)
  desktop_demo_home_example_v1(project_root, paths)
  list(status = "ready")
}

# Kurse von Yahoo im fertigen Demo (#487, rc.414). Nur nach
# der Kenntnisnahme der Hinweise und Bedingungen des Anbieters durch den Nutzer - der Aufrufer prueft sie. Steht in der Marke schon
# "active", geschieht nichts; "partial" und "unreachable" werden erneut versucht. Liefert list(status = "active"|"partial"|"unreachable"|
# "failed", verified, total, code). Das Demo bleibt in jedem Fall vollstaendig (Rueckweg je Asset in scripts/desktop_demo_market.R).
desktop_demo_home_market_v1 <- function(project_root, paths, say = function(step) invisible(NULL)) {
  marker <- desktop_demo_home_marker_read_v1(paths$state)
  if (!is.list(marker) || !identical(marker$origin, "release") || !identical(marker$status, "ready"))
    return(list(status = "failed", code = "desktop_demo_home_market_failed"))
  if (identical(marker$prices, "yahoo") && identical(marker$prices_status, "active")) return(list(status = "active", already = TRUE))
  rscript <- file.path(R.home("bin"), "Rscript")
  script <- file.path(project_root, "scripts", "desktop_demo_market.R")
  if (!file.exists(rscript) || !file.exists(script)) return(list(status = "failed", code = "desktop_demo_home_runner_missing"))
  result <- .desktop_demo_home_stream_v1(rscript, script, desktop_demo_home_env_v1(paths), say)
  last <- Filter(function(value) identical(value$step, "market"), result$values)
  outcome <- if (length(last)) last[[length(last)]] else list(status = "failed", code = "desktop_demo_home_market_failed")
  status <- if (isTRUE(outcome$status %in% c("active", "partial", "unreachable"))) outcome$status else "failed"
  marker$prices <- if (status %in% c("active", "partial")) "yahoo" else "none"
  marker$prices_status <- status
  marker$prices_at_utc <- .desktop_demo_home_stamp_v1()
  desktop_demo_home_marker_write_v1(paths$state, marker)
  list(status = status, verified = outcome$verified, total = outcome$total,
       code = if (identical(status, "failed")) (if (is.character(outcome$code)) outcome$code else "desktop_demo_home_market_failed") else outcome$code)
}

# --- Demo aus dem Einrichtungsdialog (#487 Teil 2, rc.413) ---------------------------------------------------------------------
#
# Der Dialog startet `portelyra_desktop.R demo` als eigenen Prozess in eigener Sitzung (setsid) und zeigt dessen Fortschritt aus dem
# Protokoll. Ein so gestartetes Demo hat kein Terminal, in dem man es beendet: Es endet deshalb mit dem Portelyra, das es gestartet hat
# (das Startskript ruft beim Beenden desktop_demo_home_stop_spawned_v1). Dafuer vermerkt der Demo-Prozess sich selbst im eigenen Home
# (demo-session.json: Prozessnummer und Startzeit des Prozesses, gegen wiederverwendete Nummern).

desktop_demo_home_session_path_v1 <- function(home) file.path(home, "demo-session.json")
desktop_demo_home_log_path_v1 <- function(home) file.path(home, "demo-start.log")

# Zustand und Startzeit eines Prozesses aus /proc; NULL, wenn es ihn nicht gibt oder er nur noch als Zombie haengt.
.desktop_demo_home_process_v1 <- function(pid) {
  pid <- suppressWarnings(as.integer(pid))
  if (length(pid) != 1L || is.na(pid) || pid <= 1L) return(NULL)
  text <- suppressWarnings(tryCatch(readLines(sprintf("/proc/%d/stat", pid), n = 1L, warn = FALSE), error = function(error) character()))
  if (!length(text)) return(NULL)
  rest <- strsplit(sub("^.*\\) ", "", text), " ", fixed = TRUE)[[1L]]
  if (length(rest) < 20L || identical(rest[[1L]], "Z")) return(NULL)
  list(pid = pid, start = rest[[20L]])
}
.desktop_demo_home_alive_v1 <- function(pid, process_start) {
  process <- .desktop_demo_home_process_v1(pid)
  !is.null(process) && is.character(process_start) && length(process_start) == 1L && identical(process$start, process_start)
}
.desktop_demo_home_read_json_v1 <- function(path) {
  if (!file.exists(path) || nzchar(Sys.readlink(path))) return(NULL)
  value <- tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(error) NULL)
  if (is.list(value)) value else NULL
}

# Laeuft das Demo (haelt ein lebender Prozess die Sitzungssperre des Demo-Homes)?
desktop_demo_home_running_v1 <- function(paths) {
  owner <- .desktop_demo_home_read_json_v1(file.path(paths$home, "desktop-session.lock", "owner.json"))
  is.list(owner) && .desktop_demo_home_alive_v1(owner$pid, as.character(owner$process_start))
}

# Der Demo-Prozess vermerkt sich selbst (nur wenn der Dialog ihn gestartet hat: PORTELYRA_DEMO_SESSION_FILE).
desktop_demo_home_session_write_v1 <- function(path, paths) {
  if (!is.character(path) || length(path) != 1L || !startsWith(path, "/") || grepl("[[:cntrl:]]", path) || !dir.exists(dirname(path))) return(invisible(FALSE))
  own <- .desktop_demo_home_process_v1(Sys.getpid())
  if (is.null(own)) return(invisible(FALSE))
  staged <- paste0(path, ".neu")
  old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
  writeLines(as.character(jsonlite::toJSON(list(contract_version = "portelyra_demo_session_v1", pid = own$pid, process_start = own$start,
    started_at_utc = .desktop_demo_home_stamp_v1(), demo_home = paths$home, demo_state = paths$state), auto_unbox = TRUE)), staged, useBytes = TRUE)
  Sys.chmod(staged, "0600", use_umask = FALSE)
  invisible(file.rename(staged, path))
}
desktop_demo_home_session_read_v1 <- function(home) {
  value <- .desktop_demo_home_read_json_v1(desktop_demo_home_session_path_v1(home))
  if (is.list(value) && identical(value$contract_version, "portelyra_demo_session_v1")) value else NULL
}
.desktop_demo_home_session_alive_v1 <- function(record) is.list(record) && .desktop_demo_home_alive_v1(record$pid, as.character(record$process_start))

# Startet das Demo aus dem Dialog. `browser`: die Kennung des Browsers, in dem das eigene Portelyra oeffnet ("firefox", "chromium" …; seit
# 0.3.3 jede aus der Browserwahl, #586), "none" (kein Browser) oder leer bzw. "default" (der uebliche Browser). Liefert
# list(status = "started" | "running" | "failed", code).
desktop_demo_home_spawn_v1 <- function(project_root, home, browser = "", wait_seconds = 20, prices = "none") {
  if (!identical(prices, "none") && !identical(prices, "yahoo")) return(list(status = "failed", code = "desktop_demo_home_terms_required"))
  paths <- desktop_demo_home_paths_v1()
  problem <- desktop_demo_home_guard_v1(paths, own_home = home)
  if (!is.null(problem)) return(list(status = "failed", code = problem))
  if (identical(desktop_demo_home_status_v1(paths)$status, "foreign")) return(list(status = "failed", code = "desktop_demo_home_not_empty"))
  # Laeuft es schon (aus dem Terminal oder einem frueheren Klick), wird nichts Zweites gestartet.
  if (desktop_demo_home_running_v1(paths)) return(list(status = "running"))
  if (.desktop_demo_home_session_alive_v1(desktop_demo_home_session_read_v1(home))) return(list(status = "started", already = TRUE))
  rscript <- file.path(R.home("bin"), "Rscript")
  launcher <- file.path(project_root, "scripts", "portelyra_desktop.R")
  setsid <- unname(Sys.which("setsid"))
  if (!file.exists(rscript) || !file.exists(launcher) || !nzchar(setsid)) return(list(status = "failed", code = "desktop_demo_home_runner_missing"))
  session <- desktop_demo_home_session_path_v1(home); log <- desktop_demo_home_log_path_v1(home)
  unlink(session)
  # Kurse von Yahoo nur, wenn der Nutzer im Dialog die Hinweise und Bedingungen des Anbieters zur Kenntnis genommen hat (prices = "yahoo").
  named <- is.character(browser) && length(browser) == 1L && grepl("^[a-z][a-z-]*$", browser) && !browser %in% c("none", "default")
  args <- c(rscript, "--vanilla", launcher, "demo", if (identical(browser, "none")) "--no-browser" else if (named) c("--browser", browser),
            if (identical(prices, "yahoo")) c("--prices", "yahoo", "--confirm", DESKTOP_DEMO_HOME_TERMS_CONFIRM_V1))
  old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
  system2(setsid, shQuote(args), wait = FALSE, stdout = log, stderr = log, env = paste0("PORTELYRA_DEMO_SESSION_FILE=", shQuote(session)))
  deadline <- Sys.time() + wait_seconds
  while (Sys.time() < deadline) {
    if (.desktop_demo_home_session_alive_v1(desktop_demo_home_session_read_v1(home))) return(list(status = "started"))
    Sys.sleep(0.25)
  }
  list(status = "failed", code = "desktop_demo_home_start_timeout")
}

# Fortschritt des aus dem Dialog gestarteten Demos, gelesen aus seinem Protokoll:
#   waiting (noch keine Zeile) -> building (Aufbau, mit Schritten) -> starting (aufgebaut, Apps starten) -> started (laeuft, mit Ports);
#   blocked (mit Grund), ended (Prozess beendet).
desktop_demo_home_progress_v1 <- function(home) {
  log <- desktop_demo_home_log_path_v1(home)
  lines <- if (file.exists(log)) suppressWarnings(tryCatch(readLines(log, warn = FALSE), error = function(error) character())) else character()
  values <- .desktop_demo_home_json_lines_v1(lines[startsWith(lines, "{")])
  status_of <- function(value) if (is.character(value$status) && length(value$status) == 1L) value$status else ""
  statuses <- vapply(values, status_of, character(1L))
  steps <- lapply(values[statuses == "demo_step"], function(value) list(step = as.character(value$step), result = if (is.null(value$result)) "" else as.character(value$result),
                                                                       asset = if (is.character(value$asset)) value$asset else NULL))
  market <- values[statuses == "demo_market"]
  market <- if (length(market)) market[[length(market)]] else NULL
  alive <- .desktop_demo_home_session_alive_v1(desktop_demo_home_session_read_v1(home))
  if (any(statuses == "blocked")) {
    last <- values[[max(which(statuses == "blocked"))]]
    return(list(phase = "blocked", code = if (is.character(last$code)) last$code else "desktop_demo_home_build_failed", steps = steps))
  }
  if (length(values) && !alive) return(list(phase = "ended", steps = steps))
  if (any(statuses == "starting")) {
    ports <- values[[max(which(statuses == "starting"))]]$ports
    return(list(phase = "started", steps = steps, port = if (is.list(ports) && !is.null(ports$data)) as.integer(ports$data) else NULL,
                market = if (is.list(market)) market$result else NULL))
  }
  phase <- if (any(statuses == "demo_market") || any(statuses == "demo_ready") && !any(statuses == "demo_market_starting")) "starting"
           else if (any(statuses == "demo_market_starting")) "market" else if (any(statuses == "demo_building")) "building" else "waiting"
  list(phase = phase, steps = steps, market = if (is.list(market)) market$result else NULL)
}

# Beendet ein Demo, das der Dialog dieses Homes gestartet hat - beim Beenden des eigenen Portelyra. Laufen die Apps des Demos, bekommt
# der Inhaber seiner Sitzungssperre ein SIGINT (wie Strg+C); waehrend des Aufbaus endet die ganze Prozessgruppe (der Aufbau wird beim
# naechsten Aufruf fortgesetzt). Ein Demo aus dem Terminal oder aus dem Entwicklerwerkzeug bleibt unberuehrt: Es hat hier keinen Vermerk.
desktop_demo_home_stop_spawned_v1 <- function(home, wait_seconds = 40) {
  record <- desktop_demo_home_session_read_v1(home)
  if (!is.list(record)) return(invisible("none"))
  on.exit(unlink(desktop_demo_home_session_path_v1(home)), add = TRUE)
  alive <- function() .desktop_demo_home_session_alive_v1(record)
  if (!alive()) return(invisible("gone"))
  group_end <- function() suppressWarnings(system2("kill", c("-TERM", paste0("-", as.integer(record$pid))), stdout = FALSE, stderr = FALSE))
  owner <- if (is.character(record$demo_home)) .desktop_demo_home_read_json_v1(file.path(record$demo_home, "desktop-session.lock", "owner.json")) else NULL
  if (is.list(owner) && .desktop_demo_home_alive_v1(owner$pid, as.character(owner$process_start))) tools::pskill(as.integer(owner$pid), tools::SIGINT) else group_end()
  deadline <- Sys.time() + wait_seconds
  while (alive() && Sys.time() < deadline) Sys.sleep(0.25)
  if (alive()) { group_end(); Sys.sleep(1) }
  invisible(if (alive()) "still_running" else "stopped")
}
