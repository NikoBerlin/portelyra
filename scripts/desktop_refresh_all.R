# „Alles aktualisieren“ als eigener Prozess (rc.315, #510): dieselbe Schrittmaschine wie bisher, ohne Shiny-Sitzung.
#
# Aufruf (die Data-App startet ihn, spaeter auch ein Zeitplan):
#   Rscript scripts/desktop_refresh_all.R --home <Portelyra-Home> --run-id <run_...>|auto --origin app|timer --retry-gaps yes|no|weekly
#     [--only moment] [--wait-seconds <0-3600>] --confirm RUN_REFRESH_ALL
# Seit rc.365 (#516): `--only moment` laeuft nur die Momentaufnahme (eigener Zeitplan, eigener Stand), `--retry-gaps weekly` fragt
# Quellluecken nur ab, wenn das zuletzt mehr als sechseinhalb Tage her ist, und ein zeitgesteuerter Lauf wartet bis zu
# `--wait-seconds` (Vorgabe 1800) auf einen laufenden, statt sofort aufzugeben.
# Der Zeitplan (rc.316, systemd-Timer des Benutzers) ruft ihn mit --run-id auto und --origin timer auf; das Ergebnis eines solchen
# Laufs steht zusaetzlich in last-timer.json, damit es ein spaeterer Lauf aus der App nicht verdeckt.
# Die Bestaetigung steht fuer dasselbe wie das Haekchen der Karte: Kurse beim Anbieter abrufen und Bewertungen, Tageshistorie,
# Snapshot, Abschluss, Momentaufnahme und Datenbasis schreiben. Stand, Sperre und Anhalte-Bitte liegen in refresh-all-v1 des
# Datenraums (apps/data/data_refresh_all_store_v1.R). Ausgabe: eine JSON-Zeile mit dem Ende des Laufs.
# Seit rc.366 (#540) veroeffentlicht der Lauf seinen Stand fuer den Block links in allen Apps: beim Start, bei jedem Schrittwechsel,
# alle paar Assets und nach dem Freigeben der Sperre (apps/data/data_activity_status_v1.R).
# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
args_all <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("^--file=", "", args_all[grep("^--file=", args_all)][1L])
emit <- function(value) cat(as.character(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA)), "\n", sep = "")
# Vor jedem Abbruch: Hat dieser Lauf selbst entsperrt (#553), sperrt er wieder - quit() ueberspringt on.exit.
before_quit <- NULL
run_home <- NULL
block <- function(code, status = 2L) {
  if (is.function(before_quit)) try(before_quit(), silent = TRUE)
  cat(paste0('{"status":"blocked","code":"', code, '"}\n')); quit(save = "no", status = status)
}
# Passwortschutz (#535, #553): ein Befehl an den Kern; die Eingabe enthaelt nur das Home, kein Geheimnis.
protection_cli <- function(home, command) {
  python <- Sys.which("python3")
  if (!nzchar(python)) return(NULL)
  output <- tryCatch(suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(file.path(project_root, "scripts", "desktop_protection.py")), command),
                     input = as.character(jsonlite::toJSON(list(home = home), auto_unbox = TRUE)), stdout = TRUE, stderr = FALSE)), error = function(error) character())
  tryCatch(jsonlite::fromJSON(utils::tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
}
# Passwortschutz (#535, #587): Was der Benutzer entsperrt hat, bleibt bis zur Abmeldung offen. Laeuft Portelyra nicht (keine Sitzungssperre),
# sperrt der letzte Lauf an seinem Ende, was nur ein Zeitlauf geoeffnet hat, und was eingestellt oder angefordert ist.
protection_relock <- function(home) if (file.exists(file.path(home, "protection.json")) && !dir.exists(file.path(home, "desktop-session.lock")))
  invisible(protection_cli(home, "lock-after-run"))
if (!length(file_arg) || is.na(file_arg)) block("refresh_all_project_invalid")
project_root <- tryCatch(normalizePath(file.path(dirname(file_arg), ".."), winslash = "/", mustWork = TRUE), error = function(error) NULL)
if (is.null(project_root)) block("refresh_all_project_invalid")

values <- commandArgs(trailingOnly = TRUE)
options_of <- function(values) {
  result <- list(); index <- 1L
  while (index <= length(values)) {
    key <- values[[index]]
    if (!key %in% c("--home", "--run-id", "--origin", "--retry-gaps", "--confirm", "--only", "--wait-seconds") || index == length(values)) block("refresh_all_input_invalid")
    result[[sub("^--", "", key)]] <- values[[index + 1L]]; index <- index + 2L
  }
  result
}
opts <- options_of(values)
if (identical(opts[["run-id"]], "auto"))
  opts[["run-id"]] <- paste0("run_", format(Sys.time(), "%Y%m%d%H%M%S", tz = "UTC"), substr(sprintf("%08x", as.integer(stats::runif(1L) * 2^31)), 1L, 8L))
wait_seconds <- if (is.null(opts[["wait-seconds"]])) (if (identical(opts$origin, "timer")) 1800L else 0L) else suppressWarnings(as.integer(opts[["wait-seconds"]]))
if (!identical(opts$confirm, "RUN_REFRESH_ALL") || !isTRUE(opts$origin %in% c("app", "timer")) || !isTRUE(opts[["retry-gaps"]] %in% c("yes", "no", "weekly")) ||
    !(is.null(opts$only) || identical(opts$only, "moment")) || length(wait_seconds) != 1L || is.na(wait_seconds) || wait_seconds < 0L || wait_seconds > 3600L ||
    !is.character(opts[["run-id"]]) || !grepl("^run_[a-z0-9]{8,40}$", opts[["run-id"]]) || !is.character(opts$home) || !dir.exists(opts$home)) {
  block("refresh_all_input_invalid")
}
run_id <- opts[["run-id"]]
kind <- if (identical(opts$only, "moment")) "moment" else "refresh"
# Herkunft in der Sperre: Ein Lauf nur der Momentaufnahme nennt sich so, damit die Hinweise der App ihn richtig benennen.
holder_origin <- if (identical(kind, "moment") && identical(opts$origin, "timer")) "timer_moment" else opts$origin
activity <- NULL

main <- function() {
  # Kindprozesse (Python) duerfen kein __pycache__ in das versiegelte Abbild schreiben.
  Sys.setenv(PYTHONDONTWRITEBYTECODE = "1")
  # Zeitlauf-Merkmal fuer alle Kindprozesse (rc.391, #546): Kostenpflichtige Kursanbieter rufen dann nur ab, wenn sie fuer den Zeitlauf
  # eingeschaltet sind - auch wenn ein einzelner Schritt die Herkunft nicht durchreicht. Das Merkmal kann nur sperren.
  if (identical(opts$origin, "timer")) Sys.setenv(PORTELYRA_RUN_ORIGIN = "timer")
  home <- normalizePath(opts$home, winslash = "/", mustWork = TRUE)
  run_home <<- home
  library_path <- file.path(home, "library")
  if (dir.exists(library_path)) .libPaths(c(library_path, .libPaths()))
  if (!requireNamespace("spotcore", quietly = TRUE) || !requireNamespace("jsonlite", quietly = TRUE)) block("refresh_all_dependency_missing")
  suppressPackageStartupMessages(library(spotcore))
  runtime <- tryCatch(spotcore::desktop_product_runtime_load_v1(home), error = function(error) error)
  locked <- function(value) inherits(value, "error") && identical(tryCatch(value$code, error = function(error) NULL), "desktop_product_locked")
  # Mit der Anmeldung entsperren (#553): Gesperrt entsperrt der Lauf selbst ueber den Schluesselbund. Die Einhaengung gehoert der Sitzung,
  # nicht diesem Lauf (#587): Eine waehrenddessen geoeffnete App behaelt ihren Bestand, wenn der Lauf endet.
  reason <- NULL
  if (locked(runtime)) {
    unlocked <- protection_cli(home, "unlock-for-run")
    if (is.list(unlocked) && identical(unlocked$status, "completed") && isTRUE(unlocked$result$unlocked)) {
      before_quit <<- function() protection_relock(home)
      runtime <- tryCatch(spotcore::desktop_product_runtime_load_v1(home), error = function(error) error)
    } else reason <- if (is.list(unlocked) && is.character(unlocked$code)) unlocked$code else "desktop_protection_locked"
  }
  # Passwortschutz (#535): Gesperrt laeuft kein Zeitlauf. Festgehalten wird nur, dass, wann und warum er ausfiel (ohne Inhalte), damit die
  # Data-App nach dem Entsperren sagen kann, was nachzuholen ist.
  if (locked(runtime)) {
    marker <- file.path(home, "protection-skipped.json")
    previous <- tryCatch(jsonlite::fromJSON(marker, simplifyVector = FALSE), error = function(error) list())
    entries <- utils::tail(c(if (is.list(previous$skipped)) previous$skipped else list(),
      list(list(origin = opts$origin, kind = if (identical(opts$only, "moment")) "moment" else "refresh", reason = reason,
                at_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")))), 20L)
    tryCatch({ writeLines(as.character(jsonlite::toJSON(list(skipped = entries), auto_unbox = TRUE)), marker); Sys.chmod(marker, "0600") },
             error = function(error) NULL)
    block("refresh_all_locked")
  }
  if (inherits(runtime, "error") || is.null(runtime)) block("refresh_all_runtime_invalid")
  options(portelyra.desktop.project_root = project_root, portelyra.desktop.runtime = runtime)
  # Installierte Kursanbieter dieses Datenraums (#486 Schritt 3): fuer alle abrufenden Unterprozesse des Laufs.
  Sys.setenv(PORTELYRA_INSTALLED_PRICE_PROVIDERS = file.path(spotcore::runtime_data_space_path(runtime$context), "price-provider-plugins-v1"))
  source(file.path(project_root, "apps", "data", "data_refresh_all_deps_v1.R"), local = .GlobalEnv)
  for (file in data_refresh_all_sources_v1(project_root)) source(file.path(project_root, file), local = .GlobalEnv)
  store <- data_refresh_all_store_v1(spotcore::runtime_data_space_path(runtime$context))
  # Trifft ein Lauf auf einen laufenden, wartet er bis zu `wait_seconds` (rc.365, #516: zwei Zeitplaene blockieren sich nicht,
  # der zweite kommt danach). Wer danach immer noch nicht darf, haelt das fest - sonst bliebe der Ausfall unsichtbar.
  deadline <- Sys.time() + wait_seconds
  while (!store$acquire(run_id, holder_origin)) {
    if (Sys.time() >= deadline) {
      if (identical(opts$origin, "timer")) store$write_last_timer(list(run_id = run_id, origin = "timer", running = FALSE, index = 0L, steps = list(),
        started_at_utc = store$utc(), finished_at_utc = store$utc(), notice = list(tone = "warning", title = "Nicht gestartet",
          copy = paste0("Zur geplanten Zeit lief schon ", data_refresh_all_holder_text_v1(store$holder()) %||% "ein Lauf, ein Sammellauf oder eine Wartung",
                        if (wait_seconds > 0L) paste0("; auch nach ", if (wait_seconds >= 60L) paste(wait_seconds %/% 60L, "Minuten") else paste(wait_seconds, "Sekunden"),
                                                      " Warten nicht frei") else "",
                        ". Der nächste Termin versucht es wieder."))), kind)
      block("refresh_all_already_running", 3L)
    }
    Sys.sleep(min(30, max(1, as.numeric(difftime(deadline, Sys.time(), units = "secs")))))
  }
  on.exit(store$release(run_id), add = TRUE)
  # Gewaehlte Fassung des Steuermoduls im Datenraum sichern (#486 Schritt 2): Beim Oeffnen der Steuereinstellungen und bei jeder Uebernahme geschieht das schon; hier, damit sie auch
  # ohne geoeffnete Einstellungen vorliegt, bevor ein spaeteres Release sie nicht mehr mitbringt. Nur beim grossen Lauf; scheitert es, laeuft
  # der Lauf weiter.
  if (identical(kind, "refresh")) tryCatch({
    tax_store <- file.path(spotcore::runtime_data_space_path(runtime$context), "tax-ui", "tax-policy.sqlite")
    if (file.exists(tax_store)) invisible(suppressWarnings(system2(Sys.which("python3"), c("-B", "-E", "-s",
      shQuote(file.path(project_root, "scripts", "tax_ui_workspace.py")), "preserve-modules", "--store", shQuote(tax_store),
      "--tenant-id", runtime$context$tenant_id, "--user-id", runtime$context$user_id, "--data-space-id", runtime$context$data_space_id,
      "--actor-id", "refresh_all"), stdout = FALSE, stderr = FALSE)))
  }, error = function(error) NULL)
  activity <<- tryCatch(data_activity_publisher_v1(project_root, runtime$context, function() data_activity_status_v1(store)), error = function(error) NULL)
  publish <- function(force = FALSE) if (!is.null(activity)) tryCatch(activity$tick(force), error = function(error) NULL)
  stamp <- function(value) c(value, list(run_id = run_id, origin = opts$origin, kind = kind, pid = Sys.getpid(), updated_at_utc = store$utc()))
  deps <- tryCatch(data_refresh_all_deps_v1(project_root, runtime), error = function(error) error)
  if (inherits(deps, "error")) {
    store$write_state(stamp(list(running = FALSE, index = 0L, steps = list(), started_at_utc = store$utc(), finished_at_utc = store$utc(),
      notice = list(tone = "error", title = "Nicht gestartet",
        copy = paste("Die Bausteine des Laufs ließen sich nicht laden. Sicherer Fehlercode:", spotcore::desktop_product_safe_error_code_v1(deps))))), kind)
    store$write_last_run(store$read_state(kind), kind)
    return(list(status = "blocked", code = "refresh_all_deps_invalid"))
  }
  engine <- data_refresh_all_engine_v1(deps)
  # Einmal pro Woche (rc.365): wenn die letzte Abfrage der Quellluecken mehr als sechseinhalb Tage zurueckliegt.
  retry_gaps <- switch(opts[["retry-gaps"]], yes = TRUE, no = FALSE,
    weekly = data_refresh_all_gaps_due_v1(store$read_gaps_done(), Sys.time()))
  engine$start(retry_gaps && identical(kind, "refresh"), only = if (identical(kind, "moment")) "moment" else NULL)
  store$write_state(stamp(engine$state()), kind)
  publish(TRUE)
  while (engine$running()) {
    if (store$stop_requested(run_id)) { engine$stop(); store$write_state(stamp(engine$state()), kind); break }
    engine$tick()
    store$write_state(stamp(engine$state()), kind)
    store$heartbeat(run_id)
    publish()
    # Waehrend des Sammelabrufs genuegt ein langsamerer Takt; den Abstand zwischen zwei Assets haelt der Sammelabruf selbst ein.
    Sys.sleep(if (engine$waiting()) 1 else 0.05)
  }
  final <- engine$state()
  gaps <- Filter(function(step) identical(step$code, "gaps"), final$steps)
  if (isTRUE(retry_gaps) && length(gaps) && gaps[[1L]]$status %in% c("done", "skipped") && !identical(gaps[[1L]]$copy, "nicht gewählt"))
    store$write_gaps_done()
  if (identical(opts$origin, "timer")) store$write_last_timer(stamp(final), kind)
  store$write_last_run(stamp(final), kind)
  list(status = "finished", run_id = run_id, tone = if (is.list(final$notice)) final$notice$tone else NULL)
}
# Passwortschutz (#535, #553): gesperrt wird erst nach dem letzten Schreiben - auch nach dem abschliessenden Stand unten. Frueher (als erster
# Aufraeumschritt in main) landete dieser Stand im leeren Einhaengeordner unter /run/user.
result <- tryCatch(main(), error = function(error) { if (!is.null(run_home)) protection_relock(run_home); stop(error) })
# Erst jetzt ist die Sperre frei: Der veroeffentlichte Stand zeigt den Lauf als beendet.
if (!is.null(activity)) tryCatch(activity$tick(TRUE), error = function(error) NULL)
if (!is.null(run_home)) protection_relock(run_home)
emit(result)
