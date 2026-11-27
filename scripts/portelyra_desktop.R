bootstrap_block <- function(code) {
  cat(paste0('{"status":"blocked","code":"', code, '"}\n'))
  quit(save = "no", status = 2L)
}
args_all <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("^--file=", "", args_all[grep("^--file=", args_all)][1L])
if (!length(file_arg) || is.na(file_arg)) bootstrap_block("desktop_product_project_invalid")
project_root <- tryCatch(
  normalizePath(file.path(dirname(file_arg), ".."), winslash = "/", mustWork = TRUE),
  error = function(error) NULL
)
if (is.null(project_root)) bootstrap_block("desktop_product_project_invalid")
tryCatch({
  source(file.path(project_root, "packages", "spotcore", "R", "runtime_context.R"), local = .GlobalEnv)
  source(file.path(project_root, "packages", "spotcore", "R", "canonical_repository.R"), local = .GlobalEnv)
  source(file.path(project_root, "packages", "spotcore", "R", "catalog_data_command.R"), local = .GlobalEnv)
  source(file.path(project_root, "packages", "spotcore", "R", "desktop_product_runtime_v1.R"), local = .GlobalEnv)
  source(file.path(project_root, "packages", "spotcore", "R", "desktop_derivative_capability_v1.R"), local = .GlobalEnv)
  source(file.path(project_root, "packages", "spotcore", "R", "desktop_release_v1.R"), local = .GlobalEnv)
  # Einstellungen der Installation und Browserwahl (#586, 0.3.3).
  source(file.path(project_root, "apps", "shared", "desktop_installation_v1.R"), local = .GlobalEnv)
}, error = function(error) bootstrap_block("desktop_product_project_invalid"))
if (!requireNamespace("jsonlite", quietly = TRUE)) bootstrap_block("desktop_product_dependency_missing")

arguments <- commandArgs(trailingOnly = TRUE)
command <- if (length(arguments)) arguments[[1L]] else "help"
rest <- if (length(arguments) > 1L) arguments[-1L] else character()

parse_options <- function(values) {
  result <- list(no_browser = FALSE)
  index <- 1L
  while (index <= length(values)) {
    key <- values[[index]]
    if (identical(key, "--no-browser")) {
      result$no_browser <- TRUE
      index <- index + 1L
      next
    }
    # Nur fuer start (#555): ohne Einrichtungsdialog, etwa fuer Tests und Werkzeuge an einem frischen Home.
    if (identical(key, "--skip-setup")) {
      if (!is.null(result$skip_setup)) stop("desktop_product_cli_input_invalid", call. = FALSE)
      result$skip_setup <- TRUE
      index <- index + 1L
      next
    }
    # Nur fuer start und stop (#570): Hinweise ueber notify-send, fuer den Starter ohne Terminal.
    if (identical(key, "--notify")) {
      if (!is.null(result$notify)) stop("desktop_product_cli_input_invalid", call. = FALSE)
      result$notify <- TRUE
      index <- index + 1L
      next
    }
    # Nur fuer update (#562 Paket 4): eine Seite zeigt den Fortschritt (Update aus der App).
    if (identical(key, "--page")) {
      if (!is.null(result$page)) stop("desktop_product_cli_input_invalid", call. = FALSE)
      result$page <- TRUE
      index <- index + 1L
      next
    }
    # Nur fuer demo (#487): das Demo aufbauen, aber nicht starten.
    if (identical(key, "--no-start")) {
      if (!is.null(result$no_start)) stop("desktop_product_cli_input_invalid", call. = FALSE)
      result$no_start <- TRUE
      index <- index + 1L
      next
    }
    if (!key %in% c("--confirm", "--label", "--port", "--target", "--bundle", "--archive", "--restored-home", "--browser", "--root", "--keep", "--plan", "--origin", "--prices", "--progress") || index == length(values)) {
      stop("desktop_product_cli_input_invalid", call. = FALSE)
    }
    name <- sub("^--", "", key)
    if (!is.null(result[[name]])) stop("desktop_product_cli_input_invalid", call. = FALSE)
    result[[name]] <- values[[index + 1L]]
    index <- index + 2L
  }
  result
}

emit <- function(value) {
  cat(as.character(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA)), "\n", sep = "")
}

safe_main <- function(expression) {
  tryCatch(
    force(expression),
    spot_desktop_product_error_v1 = function(error) {
      emit(list(status = "blocked", code = error$code))
      quit(save = "no", status = 2L)
    },
    spot_desktop_release_error_v1 = function(error) {
      # relative_path nur bei desktop_release_source_unreadable (#568): welcher Eintrag des Datenraums unlesbar ist.
      emit(c(list(status = "blocked", code = error$code), if (is.character(error$relative_path)) list(relative_path = error$relative_path)))
      quit(save = "no", status = 2L)
    },
    spot_desktop_derivative_capability_error_v1 = function(error) {
      emit(list(status = "blocked", code = error$code))
      quit(save = "no", status = 2L)
    },
    error = function(error) {
      code <- if (identical(conditionMessage(error), "desktop_product_cli_input_invalid")) {
        "desktop_product_cli_input_invalid"
      } else "desktop_product_boundary_failed"
      emit(list(status = "blocked", code = code))
      quit(save = "no", status = 2L)
    }
  )
}

if (identical(command, "help")) {
  cat(paste(
    "Portelyra Desktop (Linux, local single user)",
    "  preflight",
    "  install --confirm INSTALL_LOCAL_RUNTIME",
    "  initialize --label <Data-Space-Label> --confirm INITIALIZE_LOCAL_DESKTOP",
    "  update --archive <release.tar.gz> --confirm UPGRADE_LOCAL_RUNTIME [--browser <name>] [--no-browser] [--port <1024-65532>] [--page]",
    "     (--page: Fortschritt auf einer eigenen Seite, Data-Port + 4; so startet Data das Update aus der App, #562)",
    "  update-check --archive <release.tar.gz>   (nur Schritt 1 von update: Signatur und Versionen pruefen, nichts einspielen, #562)",
    "     (Update in einem Befehl, nur aus dem installierten Portelyra: Archiv und Signatur pruefen, Portelyra beenden, entsperren,",
    "      Backup mit Pruefung, Upgrade, Preflight, drei Backups behalten, Start; #486, #489)",
    "  rollback --confirm ROLLBACK_LOCAL_RUNTIME",
    "  derivative-capability-preview",
    "  derivative-capability-apply --confirm DERIVAT_AKTIVIEREN",
    "  backup --target <new-bundle-directory> --confirm CREATE_OWNER_BACKUP",
    "  backup-live --confirm CREATE_OWNER_BACKUP   (bei laufendem Portelyra in den Backup-Ordner, mit Pruefung; startet „Backup anlegen“ in Data, #559)",
    "  backup-check --bundle <bundle-directory>",
    "  backup-prune --root <backup-directory> --keep <n> [--plan <plan-fingerprint> --confirm PRUNE_OWNER_BACKUPS]",
    "  restore-preflight --bundle <bundle-directory> --target <empty-product-home>",
    "  restore --bundle <bundle-directory> --target <empty-product-home> --confirm RESTORE_TO_EMPTY_DESKTOP",
    "  release-build --archive <new-release.tar.gz> --confirm BUILD_LOCAL_RELEASE",
    "  release-check --archive <release.tar.gz>",
    "  acceptance-check --bundle <bundle-directory> --restored-home <restored-product-home>",
    "  relocate --confirm BIND_RESTORED_DATA_SPACE [--origin <previous-data-space>]   (nach einem Restore an einen anderen Ort, #493)",
    "  start [--port <1024-65532>] [--browser <name>] [--no-browser] [--skip-setup] [--notify]   (erster Start: Einrichtungsdialog, #555; laeuft es schon, oeffnet es wieder, #570)",
    "  unlock [--port <1024-65532>] [--browser <name>] [--no-browser]   (Passwortschutz: nur entsperren, ohne die Apps zu starten)",
    "  stop [--notify]   (laufendes Portelyra dieses Homes ruhig beenden; nicht mitten in einer Buchung, #489; --notify: Hinweis, #570)",
    "  desktop-entry --confirm CREATE_DESKTOP_ENTRY [--browser <name>]   (Starter im Anwendungsmenue, nur aus dem installierten Portelyra, #489; --browser legt den Browser der Installation fest, #586)",
    "     <name>: default (Standardbrowser) oder firefox, chromium, google-chrome, brave, microsoft-edge, vivaldi, opera, librewolf, epiphany;",
    "     ohne --browser gilt die Wahl unter Einstellungen > Programm (#586)",
    "  demo [--port <1024-65532>] [--no-browser] [--no-start] [--prices yahoo --confirm ACKNOWLEDGE_PROVIDER_TERMS]   (Demo-Portfolio in einem eigenen Home; der erste Aufruf baut es offline auf, #487; mit Kursen von Yahoo nach Kenntnisnahme der Hinweise des Anbieters)",
    "Owner-controlled paths are CLI-only and are never accepted from Browser input or emitted in diagnostics.",
    sep = "\n"
  ), "\n")
  quit(save = "no", status = 0L)
}

options <- safe_main(parse_options(rest))
home <- safe_main(desktop_product_default_home_v1())

# Wartung und „Alles aktualisieren“ schliessen sich aus (rc.316, #510): Der Lauf ist ein eigener Prozess und kann auch
# zeitgesteuert starten. Backup, Upgrade, Rollback und Wiederherstellen halten fuer ihre Dauer dieselbe Sperre in jedem
# Datenraum; laeuft gerade ein Lauf, brechen sie mit desktop_product_refresh_running ab, statt halbe Staende zu sichern.
refresh_pause <- function(on_conflict = NULL) {
  store_file <- file.path(project_root, "apps", "data", "data_refresh_all_store_v1.R")
  if (!file.exists(store_file)) return(function() invisible(NULL))
  helpers <- new.env(parent = globalenv()); sys.source(store_file, envir = helpers)
  # Mit Passwortschutz (#535) liegt der Datenbestand in der eingehaengten Ansicht; gesperrt gibt es dort nichts zu sperren.
  data_root <- tryCatch(.desktop_product_home_paths_v1(home), error = function(error) NULL)
  data_root <- if (is.list(data_root) && !isTRUE(data_root$locked)) data_root$data_root else file.path(home, "data")
  spaces <- Filter(function(path) file.exists(file.path(path, "canonical.sqlite")), Sys.glob(file.path(data_root, "*", "*", "*")))
  run_id <- paste0("run_maint", format(Sys.time(), "%Y%m%d%H%M%S", tz = "UTC"))
  held <- list(); keeper <- NULL
  release <- function() {
    if (!is.null(keeper)) { tryCatch(tools::pskill(keeper$pid), error = function(error) NULL); tryCatch(parallel::mccollect(keeper, wait = FALSE), error = function(error) NULL) }
    for (store in held) tryCatch(store$release(run_id), error = function(error) NULL); invisible(NULL)
  }
  for (space in spaces) {
    store <- tryCatch(helpers$data_refresh_all_store_v1(space), error = function(error) NULL)
    if (is.null(store)) next
    if (!isTRUE(tryCatch(store$acquire(run_id, "maintenance"), error = function(error) FALSE))) {
      release()
      if (is.function(on_conflict)) on_conflict()
      emit(list(status = "blocked", code = "desktop_product_refresh_running"))
      quit(save = "no", status = 2L)
    }
    held[[length(held) + 1L]] <- store
  }
  # Die Sperre gilt als verwaist, wenn ihr Herzschlag 20 Minuten aussetzt. Backup samt Pruefung kann bei grossen oder verschluesselten
  # Bestaenden laenger dauern - ein Zeitlauf haette die Sperre dann uebernommen und mitten ins Backup geschrieben (Prüfung 13.11.2026).
  # Ein Begleitprozess erneuert den Herzschlag jede Minute, solange dieser Prozess lebt.
  if (length(held) && requireNamespace("parallel", quietly = TRUE)) {
    parent <- Sys.getpid()
    keeper <- tryCatch(parallel::mcparallel({
      repeat {
        Sys.sleep(60)
        if (!isTRUE(tryCatch(tools::pskill(parent, 0L), error = function(error) FALSE))) break
        for (store in held) tryCatch(store$keep(run_id), error = function(error) NULL)
      }
    }, silent = TRUE), error = function(error) NULL)
  }
  release
}

# Wartung unter der Sperre (rc.416): Scheitert der Schritt, gibt das die Sperre frei, bevor safe_main das Programm beendet. Bis rc.415
# blieb sie nach einem Fehler stehen und galt erst als verwaist, als ihr Prozess beendet war (bei einem Rollout).
paused <- function(expression, resume) tryCatch(expression, error = function(error) { resume(); stop(error) })

if (identical(command, "preflight")) {
  if (length(setdiff(names(options), "no_browser")) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  safe_main(emit(desktop_product_preflight_v1(project_root, home)))
  quit(save = "no", status = 0L)
}

if (identical(command, "install")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "confirm"))) || isTRUE(options$no_browser)) {
    safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  }
  safe_main(emit(desktop_product_install_v1(project_root, home, options$confirm)))
  quit(save = "no", status = 0L)
}

if (identical(command, "initialize")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "confirm", "label"))) || isTRUE(options$no_browser)) {
    safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  }
  preflight <- safe_main(desktop_product_preflight_v1(project_root, home))
  if (!preflight$status %in% c("ready_to_initialize", "ready_to_start")) {
    safe_main(.desktop_product_abort_v1("desktop_product_dependency_missing"))
  }
  created_at <- format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  safe_main(emit(desktop_product_runtime_initialize_v1(home, options$label, created_at, options$confirm)))
  quit(save = "no", status = 0L)
}

# Updates nur noch ueber `update --archive` (#486 Schritt 3): Es prueft das Archiv aus
# dem installierten Portelyra, bevor Code daraus laeuft. `dev-upgrade` spielt den Code dieses Ordners ohne Signaturpruefung ein - nur fuer
# Entwicklung und Tests, nicht in der Hilfe. Das alte `upgrade` verweist auf den neuen Weg.
if (identical(command, "upgrade")) {
  emit(list(status = "blocked", code = "desktop_product_use_update_archive"))
  quit(save = "no", status = 2L)
}
if (identical(command, "dev-upgrade")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "confirm"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  resume <- refresh_pause()
  result <- safe_main(paused(desktop_product_upgrade_v1(project_root, home, options$confirm), resume))
  resume(); safe_main(emit(result))
  quit(save = "no", status = 0L)
}
if (identical(command, "rollback")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "confirm"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  resume <- refresh_pause()
  result <- safe_main(paused(desktop_product_rollback_v1(project_root, home, options$confirm), resume))
  resume(); safe_main(emit(result))
  quit(save = "no", status = 0L)
}
load_active_derivative_capability <- function() {
  preflight <- desktop_product_preflight_v1(project_root, home)
  if (!preflight$status %in% c("ready_to_start", "upgrade_required") ||
      !isTRUE(preflight$checks$local_packages_installed) ||
      !isTRUE(preflight$checks$runtime_registry_initialized) ||
      isTRUE(preflight$checks$upgrade_recovery_required)) {
    .desktop_product_abort_v1("desktop_product_not_initialized")
  }
  active_root <- .desktop_product_active_source_v1(home)
  required <- file.path(active_root, c(
    "packages/spotcore/R/runtime_context.R", "packages/spotcore/R/canonical_repository.R",
    "packages/spotcore/R/catalog_data_command.R", "packages/spotcore/R/desktop_product_runtime_v1.R",
    "packages/spotcore/R/desktop_derivative_capability_v1.R"
  ))
  if (any(!file.exists(required))) .desktop_product_abort_v1("desktop_product_dependency_missing")
  for (path in required) source(path, local = .GlobalEnv)
  list(
    runtime = desktop_product_runtime_load_v1(home),
    contract_root = file.path(active_root, "contracts")
  )
}
derivative_capability_cli_public <- function(value) {
  allowed <- c(
    "contract_version", "status", "source_schema_version", "target_schema_version", "counts",
    "confirmation_required", "product_write", "activity_write", "cash_write", "committed_at_utc",
    "generic_derivative_catalog_enabled", "generic_derivative_activity_enabled_by_release_patch",
    "derivative_coupled_transaction_enabled", "lifecycle_metadata_inferred",
    "automatic_cash_posting_enabled", "provider_access", "network_access"
  )
  value[intersect(allowed, names(value))]
}
if (identical(command, "derivative-capability-preview")) {
  if (length(setdiff(names(options), "no_browser")) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  active <- safe_main(load_active_derivative_capability())
  preview <- safe_main(desktop_derivative_capability_preview_v1(active$runtime$context, active$contract_root))
  safe_main(emit(derivative_capability_cli_public(preview)))
  quit(save = "no", status = 0L)
}
if (identical(command, "derivative-capability-apply")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "confirm"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  run_apply <- function() {
    session_lock <- file.path(home, "desktop-session.lock")
    owner <- .desktop_product_acquire_lock_v1(session_lock, "desktop_product_session_conflict")
    on.exit(if (dir.exists(session_lock)) .desktop_product_release_lock_v1(session_lock, owner), add = TRUE)
    active <- load_active_derivative_capability()
    preview <- desktop_derivative_capability_preview_v1(active$runtime$context, active$contract_root)
    if (!identical(preview$status, "ready_for_confirmation")) return(preview)
    confirmed <- format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    expires <- format(as.POSIXct(confirmed, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") + 300, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    confirmation <- desktop_derivative_capability_confirmation_v1(preview, options$confirm, confirmed, expires)
    desktop_derivative_capability_apply_v1(
      active$runtime$context, active$contract_root, preview, confirmation,
      new_desktop_derivative_capability_authorizer_v1(), confirmed
    )
  }
  safe_main(emit(derivative_capability_cli_public(run_apply())))
  quit(save = "no", status = 0L)
}
if (identical(command, "backup")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "confirm", "target"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  resume <- refresh_pause()
  result <- safe_main(paused(desktop_release_backup_v1(project_root, home, options$target, options$confirm), resume))
  resume(); safe_main(emit(result))
  quit(save = "no", status = 0L)
}
# Backup aus der laufenden App (#559, rc.407): „Backup anlegen“ in Data startet diesen Befehl als eigenen Prozess. Er haelt die
# Wartungssperre (Zeitlaeufe, „Alles aktualisieren“ und Sammellaeufe warten), sichert in den Backup-Ordner von Portelyra - bei Schutz den
# verschluesselten -, prueft das Backup gleich und schreibt jeden Schritt nach <home>/backup-job.json. Portelyra laeuft dabei weiter.
if (identical(command, "backup-live")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "confirm"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  source(file.path(project_root, "apps", "shared", "desktop_protection_v1.R"), local = .GlobalEnv)
  source(file.path(project_root, "apps", "shared", "desktop_backups_v1.R"), local = .GlobalEnv)
  stamp <- function() format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  job <- list(contract_version = 1L, pid = Sys.getpid(), process_start = .desktop_product_process_start_v1(), started_at_utc = stamp(),
              status = "running", phase = "pause")
  step <- function(...) { job <<- utils::modifyList(job, list(...)); desktop_backups_job_write_v1(home, job) }
  finish <- function(status, code = NULL, ...) {
    step(status = status, code = code, finished_at_utc = stamp(), ...)
    emit(list(status = status, code = code))
    quit(save = "no", status = if (identical(status, "created")) 0L else 2L)
  }
  error_code <- function(error) { code <- tryCatch(as.character(error$code), error = function(e) character()); if (length(code) == 1L) code else "desktop_release_boundary_failed" }
  step()
  if (!identical(options$confirm, "CREATE_OWNER_BACKUP")) finish("failed", "desktop_release_confirmation_required")
  resume <- refresh_pause(on_conflict = function() finish("failed", "desktop_product_refresh_running"))
  root <- desktop_backups_root_v1(project_root, home)
  if (!identical(root$status, "ready")) { resume(); finish("failed", root$code) }
  old_umask <- Sys.umask("0077")
  if (!dir.exists(root$root)) dir.create(root$root, recursive = TRUE, mode = "0700")
  Sys.umask(old_umask)
  name <- paste0("app-", format(Sys.time(), "%Y%m%d-%H%M%S"))
  step(phase = "backup", name = name, protected = isTRUE(root$protected))
  created <- tryCatch(desktop_release_backup_in_session_v1(project_root, home, file.path(root$root, name), "CREATE_OWNER_BACKUP"), error = function(error) error)
  if (inherits(created, "error")) {
    resume()
    shown <- tryCatch(created$relative_path, error = function(error) NULL)   # #568: der unlesbare Eintrag, fuer die Karte
    finish("failed", error_code(created), relative_path = if (is.character(shown) && length(shown) == 1L) shown else NULL)
  }
  step(phase = "check")
  checked <- tryCatch(desktop_release_backup_check_v1(project_root, file.path(root$root, name)), error = function(error) error)
  resume()
  if (inherits(checked, "error")) finish("failed", error_code(checked))
  finish("created", NULL, phase = "done", valid = TRUE, byte_count = checked$byte_count, file_count = checked$file_count)
}
if (identical(command, "backup-check")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "bundle"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  safe_main(emit(desktop_release_backup_check_v1(project_root, options$bundle)))
  quit(save = "no", status = 0L)
}
# Alte Backups ausduennen (#438): ohne --plan nur der Plan, mit --plan und Bestaetigung genau dieser Plan.
if (identical(command, "backup-prune")) {
  extra <- setdiff(names(options), c("no_browser", "root", "keep"))
  if (!all(c("root", "keep") %in% names(options)) || isTRUE(options$no_browser) ||
      !(length(extra) == 0L || identical(sort(extra), c("confirm", "plan")))) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  # Nur die Backups dieses Datenraums (rc.410); ohne eingerichtetes Home wie bisher nach dem juengsten gueltigen Backup.
  own_home <- if (file.exists(file.path(home, "desktop-runtime.json"))) home else NULL
  safe_main(emit(desktop_release_backup_prune_v1(project_root, options$root, options$keep, options$plan, options$confirm, home = own_home)))
  quit(save = "no", status = 0L)
}
if (identical(command, "restore-preflight")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "bundle", "target"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  safe_main(emit(desktop_release_restore_preflight_v1(project_root, options$bundle, options$target)))
  quit(save = "no", status = 0L)
}
if (identical(command, "restore")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "bundle", "confirm", "target"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  resume <- refresh_pause()
  result <- safe_main(paused(desktop_release_restore_v1(project_root, home, options$bundle, options$target, options$confirm), resume))
  resume(); safe_main(emit(result))
  quit(save = "no", status = 0L)
}
if (identical(command, "release-build")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "archive", "confirm"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  safe_main(emit(desktop_release_build_v1(project_root, options$archive, options$confirm)))
  quit(save = "no", status = 0L)
}
if (identical(command, "release-check")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "archive"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  safe_main(emit(desktop_release_check_v1(project_root, options$archive)))
  quit(save = "no", status = 0L)
}
# Nach einem Restore an einen anderen Ort (#493, Festlegung 11.11.2026 "Restore bindet neu"): den Ursprungsort pruefen und vermerken, damit
# die pfadgebundenen Speicher (Wechselkurs-Abrufe, Sammelabruf, Arbeitsliste, Bewertung, Kalender) ihre Eintraege wieder anerkennen.
if (identical(command, "relocate")) {
  if (!all(names(options) %in% c("no_browser", "confirm", "origin")) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  relocate <- function() {
    if (!identical(options$confirm, "BIND_RESTORED_DATA_SPACE")) .desktop_product_abort_v1("desktop_product_data_space_confirmation_required")
    runtime <- desktop_product_runtime_load_v1(home)
    session_lock <- file.path(home, "desktop-session.lock")
    owner <- .desktop_product_acquire_lock_v1(session_lock, "desktop_product_session_conflict")
    on.exit(if (dir.exists(session_lock)) .desktop_product_release_lock_v1(session_lock, owner), add = TRUE)
    payload <- as.character(jsonlite::toJSON(list(data_space_path = runtime_data_space_path(runtime$context), confirmed = TRUE,
                                                  origin = if (is.null(options$origin)) NULL else path.expand(options$origin)), auto_unbox = TRUE, null = "null"))
    output <- suppressWarnings(system2(Sys.which("python3"), c("-B", "-E", "-s", shQuote(file.path(project_root, "scripts", "desktop_relocation.py"))),
                                       input = payload, stdout = TRUE, stderr = FALSE))
    result <- tryCatch(jsonlite::fromJSON(utils::tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (!is.list(result)) .desktop_product_abort_v1("desktop_product_boundary_failed")
    if (identical(result$status, "blocked")) return(list(status = "blocked", code = result$code))
    list(status = result$result$status, probe_count = result$result$probe_count)
  }
  safe_main(emit(relocate()))
  quit(save = "no", status = 0L)
}
if (identical(command, "acceptance-check")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "bundle", "restored-home"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  safe_main(emit(desktop_release_private_acceptance_v1(project_root, home, options$bundle, options[["restored-home"]])))
  quit(save = "no", status = 0L)
}

# Port und Browser fuer start, unlock und update. Der Browser (#586, 0.3.3): --browser geht vor - "default" oder eine Kennung aus
# DESKTOP_BROWSERS_V1, die auf dem Rechner gefunden werden muss (sonst desktop_product_dependency_missing, vor jedem anderen Schritt) -,
# sonst die Wahl in den Einstellungen der Installation (Reiter „Programm“), sonst der Standardbrowser des Systems.
page_options <- function(options, setup = FALSE) {
  allowed <- c("no_browser", "port", "browser", if (isTRUE(setup)) c("skip_setup", "notify"))
  if (length(setdiff(names(options), allowed))) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  port <- if (is.null(options$port)) 3838L else suppressWarnings(as.integer(options$port))
  if (length(port) != 1L || is.na(port) || port < 1024L || port > 65532L ||
      (!is.null(options$port) && !identical(as.character(port), options$port))) {
    safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  }
  requested <- options$browser
  if (!is.null(requested) && !requested %in% DESKTOP_BROWSER_NAMES_V1) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  browser <- if (isTRUE(options$no_browser)) NULL else safe_main(desktop_browser_resolve_v1(home, requested))
  list(port = port, browser_name = if (is.null(browser)) "none" else browser$name, browser = browser, requested = requested)
}

# Browser je Oeffnen (#586): mit --browser fest; sonst bei jedem Oeffnen neu aus den Einstellungen, damit eine Wahl im Reiter „Programm“
# schon beim naechsten Klick auf den Starter gilt. Fehlt der gewaehlte Browser, oeffnet der Standardbrowser; das sagen eine Zeile und,
# mit --notify, ein Hinweis am Bildschirmrand (einmal je Prozess, kein Abbruch).
browser_fallback_said <- FALSE
page_browser <- function(page) {
  if (!is.null(page$requested) || is.null(page$browser)) return(page$browser)
  current <- tryCatch(desktop_browser_resolve_v1(home, NULL), error = function(error) page$browser)
  if (is.character(current$fallback) && !browser_fallback_said) {
    browser_fallback_said <<- TRUE
    emit(list(status = "browser_fallback", requested = current$fallback, opened = "default"))
    portelyra_notify(paste(DESKTOP_BROWSERS_V1[[current$fallback]]$label, "nicht gefunden"),
                     "Portelyra öffnet im Standardbrowser. Einen anderen Browser wählen Sie in Daten unter Einstellungen → Programm.")
  }
  current
}

# Start-Token fuer die Seiten vor den Apps (#563): je Seite ein neues, wie das Token der Apps. PORTELYRA_PAGE_TOKEN_INTERNAL setzt es nur
# fuer Tests und Werkzeuge (Ende-zu-Ende ohne Browserstart); ein anderes Benutzerkonto kann die Umgebung dieses Prozesses nicht setzen.
page_token_new <- function() {
  forced <- Sys.getenv("PORTELYRA_PAGE_TOKEN_INTERNAL", unset = "")
  if (grepl("^dlp_[0-9a-f]{64}$", forced)) return(forced)
  if (!requireNamespace("openssl", quietly = TRUE)) .desktop_product_abort_v1("desktop_product_dependency_missing")
  paste0("dlp_", paste(format(openssl::rand_bytes(32L)), collapse = ""))
}

# Passwortschutz (#535, rc.396): die Seite „Portelyra entsperren“ auf `port`, bis entsperrt ist; zurueck kommt der Zustand danach. Die
# Seite laeuft in einem eigenen Kindprozess: Der Start forkt danach die vier Apps, und ein Fork nach einem gelaufenen httpuv-Server ist
# nicht verlaesslich. Das Passwort geht vom Browser direkt an den Kern, nie ueber die Befehlszeile.
protection_unlock_page <- function(source_root, home, library, port, opener) {
  .libPaths(c(library, .libPaths()))
  if (!requireNamespace("shiny", quietly = TRUE) || !requireNamespace("later", quietly = TRUE)) .desktop_product_abort_v1("desktop_product_dependency_missing")
  shell_env <- new.env(parent = globalenv())
  sys.source(file.path(source_root, "apps", "shared", "portelyra_ui_shell.R"), envir = shell_env)
  source(file.path(source_root, "apps", "shared", "desktop_protection_v1.R"), local = .GlobalEnv)
  assign("portelyra_status_panel", shell_env$portelyra_status_panel, envir = .GlobalEnv)
  unlock_css <- shell_env$portelyra_ui_css()
  unlock_token <- page_token_new()
  portelyra_access_issue(unlock_token)                                                  # #570: vor dem Forken
  unlock_job <- parallel::mcparallel({
    # Das Token nur, wenn die installierte Seite es kennt: Vor einem Upgrade laeuft hier noch die vorige Version (unlock fuer Backup und
    # Upgrade, #535); ohne diese Pruefung brach das Entsperren mit "unused argument" ab (13.11.2026).
    page_args <- list(source_root, home, port, opener, css = unlock_css)
    if ("token" %in% names(formals(desktop_protection_unlock_blocking_v1))) page_args$token <- unlock_token
    do.call(desktop_protection_unlock_blocking_v1, page_args)
    TRUE
  }, silent = TRUE)
  running <- TRUE
  on.exit(if (running) try(tools::pskill(unlock_job$pid, tools::SIGTERM), silent = TRUE), add = TRUE)
  repeat {
    if (!is.null(parallel::mccollect(unlock_job, wait = FALSE, timeout = 0.5))) break
    portelyra_reopen_serve(function() if (is.function(opener)) {                     # #570: neuer Zugang je Oeffnen
      fresh <- page_token_new(); portelyra_access_issue(fresh); opener(desktop_page_url_v1(port, fresh))
    })
  }
  running <- FALSE
  desktop_protection_cli_v1(source_root, home, "status")
}

# Unlesbare Eintraege (#568): Ein in der Karte „Backups“ bestaetigter Auftrag wird hier ausgefuehrt, solange der Bestand noch gesperrt
# ist - genau die bestaetigten verschluesselten Ordner gehen in die Quarantaene im Home, nichts wird geloescht. Ohne Auftrag: nichts.
protection_quarantine_requested <- function(source_root, home) {
  if (!file.exists(file.path(home, "unreadable-quarantine-request.json"))) return(invisible(NULL))
  protection_env <- new.env(parent = globalenv())
  sys.source(file.path(source_root, "apps", "shared", "desktop_protection_v1.R"), envir = protection_env)
  result <- tryCatch(protection_env$desktop_protection_cli_v1(source_root, home, "unreadable-execute"), error = function(error) NULL)
  value <- if (is.list(result) && is.list(result$result)) result$result else list()
  emit(list(status = "protection_quarantine", result = if (is.character(value$status)) value$status else "failed",
            moved = length(value$moved), skipped = length(value$skipped),
            code = if (is.list(result) && is.character(result$code)) result$code else NULL))
  invisible(result)
}

# Einrichtungsdialog (#555): die Seite „Portelyra einrichten“ auf `port`, solange er gebraucht wird (erster Start, Entwurf). Wie die
# Entsperrseite in einem eigenen Kindprozess; erst darin werden Katalog und Dienste geladen. Zurueck kommt der Zustand danach.
setup_page <- function(source_root, home, port, opener) {
  setup_env <- new.env(parent = globalenv())
  sys.source(file.path(source_root, "apps", "shared", "desktop_setup_v1.R"), envir = setup_env)
  status <- setup_env$desktop_setup_status_v1(source_root, home)
  if (!identical(status$status, "completed") || !isTRUE(status$result$needed)) return(list(ran = FALSE))
  if (!requireNamespace("later", quietly = TRUE)) .desktop_product_abort_v1("desktop_product_dependency_missing")
  shell_env <- new.env(parent = globalenv())
  sys.source(file.path(source_root, "apps", "shared", "portelyra_ui_shell.R"), envir = shell_env)
  setup_css <- shell_env$portelyra_ui_css()
  setup_token <- page_token_new()
  portelyra_access_issue(setup_token)                                                   # #570: vor dem Forken
  setup_job <- parallel::mcparallel({
    setup_env$desktop_setup_load_v1(source_root, setup_env)
    assign("portelyra_status_panel", shell_env$portelyra_status_panel, envir = setup_env)
    page_args <- list(source_root, home, port, opener, css = setup_css)
    if ("token" %in% names(formals(setup_env$desktop_setup_blocking_v1))) page_args$token <- setup_token
    do.call(setup_env$desktop_setup_blocking_v1, page_args)
    TRUE
  }, silent = TRUE)
  running <- TRUE
  on.exit(if (running) try(tools::pskill(setup_job$pid, tools::SIGTERM), silent = TRUE), add = TRUE)
  repeat {
    if (!is.null(parallel::mccollect(setup_job, wait = FALSE, timeout = 0.5))) break
    portelyra_reopen_serve(function() if (is.function(opener)) {                     # #570: neuer Zugang je Oeffnen
      fresh <- page_token_new(); portelyra_access_issue(fresh); opener(paste0("http://127.0.0.1:", port, "?launch_token=", fresh))
    })
  }
  running <- FALSE
  after <- setup_env$desktop_setup_status_v1(source_root, home)
  # Den Schutz hat der Dialog eingerichtet, wenn sein Zustand das so vermerkt und der Klartext noch da ist.
  state_file <- file.path(home, "setup-state.json")
  recorded <- if (file.exists(state_file)) tryCatch(jsonlite::fromJSON(state_file, simplifyVector = FALSE), error = function(error) NULL) else NULL
  protection <- is.list(recorded) && identical(recorded$status, "applied") && any(vapply(recorded$results, function(item)
    identical(item$key, "protection") && isTRUE(item$status %in% c("enabled", "enabled_without_keyring")), logical(1L)))
  list(ran = TRUE, state = if (identical(after$status, "completed") && is.character(after$result$state)) after$result$state else "open",
       protection = protection)
}

# Ohne Browser (#580): die Adresse mit Zugang als Klartext auf der Fehlerausgabe - die JSON-Zeilen auf stdout bleiben, wie sie sind.
page_url_say <- function(url) message("Portelyra ist bereit. Im Browser öffnen (gilt nur für diesen Start): ", url)
page_opener <- function(options, page) if (isTRUE(options$no_browser)) page_url_say else function(url) desktop_browser_open_v1(url, page_browser(page))

# Demo-Portfolio (#487, rc.412): ein eigenes Portelyra-Home mit erfundenem Bestand auf echten Assets - eigener Ordner, eigener
# Zustandsordner, eigene Ports; der eigene Bestand bleibt unberuehrt (Schutzregeln in apps/shared/desktop_demo_home_v1.R). Der erste
# Aufruf baut es offline auf (rund drei Minuten), jeder weitere startet es nur. Gestartet wird im Vordergrund wie `start`.
if (identical(command, "demo")) {
  if (length(setdiff(names(options), c("no_browser", "no_start", "port", "browser", "prices", "confirm")))) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  source(file.path(project_root, "apps", "shared", "desktop_demo_home_v1.R"), local = .GlobalEnv)
  # Kurse von Yahoo (rc.414): nur mit der Kenntnisnahme der Hinweise und Bedingungen des Anbieters, wie die Frage „Kurse“ der Einrichtung.
  demo_prices <- if (is.null(options$prices)) "none" else options$prices
  if (!demo_prices %in% c("none", "yahoo") || (!is.null(options$confirm) && !identical(demo_prices, "yahoo"))) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  demo_port <- if (is.null(options$port)) DESKTOP_DEMO_HOME_PORT_V1 else suppressWarnings(as.integer(options$port))
  if (length(demo_port) != 1L || is.na(demo_port) || demo_port < 1024L || demo_port > 65532L ||
      (!is.null(options$port) && !identical(as.character(demo_port), options$port))) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  if (!is.null(options$browser) && !options$browser %in% DESKTOP_BROWSER_NAMES_V1) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  demo_block <- function(code, detail = NULL) {
    emit(list(status = "blocked", code = code, detail = detail))
    quit(save = "no", status = 2L)
  }
  if (identical(demo_prices, "yahoo") && !identical(options$confirm, DESKTOP_DEMO_HOME_TERMS_CONFIRM_V1)) demo_block("desktop_demo_home_terms_required")
  demo_paths <- desktop_demo_home_paths_v1()
  problem <- desktop_demo_home_guard_v1(demo_paths, own_home = home)
  if (!is.null(problem)) demo_block(problem)
  # Vom Einrichtungsdialog gestartet (rc.413): sich im Home des Aufrufers vermerken, damit dessen Portelyra das Demo beim Beenden mit beendet.
  demo_session_file <- Sys.getenv("PORTELYRA_DEMO_SESSION_FILE", unset = "")
  if (nzchar(demo_session_file)) invisible(desktop_demo_home_session_write_v1(demo_session_file, demo_paths))
  demo_state <- desktop_demo_home_status_v1(demo_paths)
  if (identical(demo_state$status, "foreign")) demo_block("desktop_demo_home_not_empty")
  # Je Schritt eine Zeile; der Zustand des Schritts steht als `result`, damit er nicht mit dem Status der Zeile zusammenfaellt.
  demo_say <- function(step) { names(step)[names(step) == "status"] <- "result"; emit(c(list(status = "demo_step"), step)) }
  if (demo_state$status %in% c("absent", "building")) {
    emit(list(status = "demo_building", resumed = identical(demo_state$status, "building")))
    built <- tryCatch(desktop_demo_home_build_v1(project_root, demo_paths, demo_say),
                      error = function(error) list(status = "failed", code = "desktop_demo_home_build_failed"))
    if (!identical(built$status, "ready")) demo_block(built$code, built$detail)
    demo_state <- desktop_demo_home_status_v1(demo_paths)
  }
  emit(list(status = "demo_ready", origin = demo_state$origin))
  # Kurse von Yahoo nur im Demo aus dem Release (eines aus dem Entwicklerwerkzeug hat sie schon). Scheitert es, laeuft das Demo mit den
  # Kursen der Buchungen weiter - die Zeile sagt es.
  if (identical(demo_prices, "yahoo") && identical(demo_state$origin, "release")) {
    emit(list(status = "demo_market_starting"))
    market <- tryCatch(desktop_demo_home_market_v1(project_root, demo_paths, demo_say),
                       error = function(error) list(status = "failed", code = "desktop_demo_home_market_failed"))
    emit(list(status = "demo_market", result = market$status, verified = market$verified, total = market$total, code = market$code))
  }
  if (isTRUE(options$no_start)) quit(save = "no", status = 0L)
  start_args <- c("--vanilla", file.path(project_root, "scripts", "portelyra_desktop.R"), "start", "--port", as.character(demo_port), "--skip-setup",
                  if (isTRUE(options$no_browser)) "--no-browser" else if (!is.null(options$browser)) c("--browser", options$browser))
  code <- system2(file.path(R.home("bin"), "Rscript"), shQuote(start_args), env = desktop_demo_home_env_v1(demo_paths))
  quit(save = "no", status = as.integer(code))
}

# Prozessbaum aus /proc: Eltern je Prozess, Befehlszeile.
process_parents <- function() {
  files <- Sys.glob("/proc/[0-9]*/stat")
  parents <- vapply(files, function(path) {
    line <- suppressWarnings(tryCatch(readLines(path, warn = FALSE, n = 1L), error = function(error) character()))
    if (length(line) != 1L) return(NA_character_)
    positions <- gregexpr(") ", line, fixed = TRUE)[[1L]]; positions <- positions[positions > 0L]
    if (!length(positions)) return(NA_character_)
    fields <- strsplit(substring(line, positions[[length(positions)]] + 2L), " ", fixed = TRUE)[[1L]]
    if (length(fields) < 2L) NA_character_ else fields[[2L]]
  }, character(1L), USE.NAMES = FALSE)
  stats::setNames(parents, basename(dirname(files)))
}
process_state <- function(pid) {
  line <- suppressWarnings(tryCatch(readLines(file.path("/proc", pid, "stat"), warn = FALSE, n = 1L), error = function(error) character()))
  if (length(line) != 1L) return("")
  positions <- gregexpr(") ", line, fixed = TRUE)[[1L]]; positions <- positions[positions > 0L]
  if (!length(positions)) "" else substr(line, positions[[length(positions)]] + 2L, positions[[length(positions)]] + 2L)
}
process_command <- function(pid) {
  raw <- tryCatch(readBin(file.path("/proc", pid, "cmdline"), "raw", 65536L), error = function(error) raw())
  if (!length(raw)) return("")
  rawToChar(replace(raw, raw == as.raw(0L), as.raw(32L)))
}
# Ein laufendes Portelyra beenden (Update Schritt 2, `stop`): nur einen Start dieses Homes, und nur wenn keine App gerade einen Kindprozess
# hat. Die Apps sind Forks des Starts (gleiche Befehlszeile); was sie selbst starten, arbeitet gerade. Ein Browser, den der Start oeffnete,
# zaehlt nicht. Gewartet wird, bis der Start und alle Apps beendet sind (der Start sperrt dabei den Datenbestand). `fail(code)` bricht ab.
portelyra_stop_running <- function(fail) {
  owner_path <- file.path(home, "desktop-session.lock", "owner.json")
  owner <- if (!file.exists(owner_path) || .desktop_product_symlink_v1(owner_path)) NULL else
    tryCatch(jsonlite::fromJSON(owner_path, simplifyVector = FALSE), error = function(error) NULL)
  if (!.desktop_product_lock_active_v1(owner)) return(FALSE)
  pid <- as.character(as.integer(owner$pid))
  start_command <- process_command(pid)
  if (!grepl("--file=.*portelyra_desktop[.]R --args start( |$)", start_command)) fail("desktop_product_session_conflict")
  parents <- process_parents()
  children <- names(parents)[!is.na(parents) & parents == pid]
  apps <- children[vapply(children, function(child) identical(process_command(child), start_command), logical(1L))]
  if (any(!is.na(parents) & parents %in% apps)) fail("desktop_product_update_busy")
  watched <- c(pid, apps)
  starts <- vapply(watched, function(item) { value <- .desktop_product_process_start_v1(as.integer(item)); if (is.null(value)) NA_character_ else value }, character(1L))
  tools::pskill(as.integer(pid), tools::SIGINT)
  deadline <- Sys.time() + 120
  repeat {
    # Beendet ist auch ein Prozess, den sein Elternprozess noch nicht abgeholt hat (Zustand Z), etwa wenn ein Werkzeug den Start hielt.
    alive <- vapply(seq_along(watched), function(index) !is.na(starts[[index]]) &&
      identical(.desktop_product_process_start_v1(as.integer(watched[[index]])), starts[[index]]) &&
      !identical(process_state(watched[[index]]), "Z"), logical(1L))
    if (!any(alive)) break
    if (Sys.time() > deadline) fail("desktop_product_update_stop_failed")
    Sys.sleep(0.5)
  }
  TRUE
}

# Hinweise ohne Terminal (#570, rc.433): nur mit --notify (der Starter setzt es), ueber notify-send. Fehler im deutschen Text des Katalogs.
# PORTELYRA_NOTIFY_COMMAND_INTERNAL ersetzt das Programm nur fuer Tests. Ohne Programm oder ohne grafische Sitzung bleibt es still.
portelyra_notify <- function(title, body = "") {
  if (!isTRUE(options$notify)) return(invisible(FALSE))
  command <- Sys.getenv("PORTELYRA_NOTIFY_COMMAND_INTERNAL", unset = "")
  if (!nzchar(command)) command <- Sys.which("notify-send")
  if (!nzchar(command)) return(invisible(FALSE))
  tryCatch(system2(command, c("--app-name=Portelyra", shQuote(paste0("--icon=", portelyra_notify_icon())), shQuote(title), shQuote(body)),
                   stdout = FALSE, stderr = FALSE, wait = FALSE), error = function(error) NULL)
  invisible(TRUE)
}
# Symbol der Hinweise (#584): die Bildmarke aus dem Symbolthema, sonst die Datei im Programm, sonst das allgemeine Symbol.
portelyra_notify_icon <- function() {
  if (file.exists(file.path(.desktop_product_data_home_v1(), "icons", "hicolor", "scalable", "apps", "portelyra.svg"))) return("portelyra")
  svg <- file.path(project_root, "apps", "shared", "icons", "portelyra.svg")
  if (file.exists(svg)) svg else "applications-office"
}
portelyra_error_text <- function(code) {
  shell_env <- new.env(parent = globalenv())
  text <- tryCatch({
    sys.source(file.path(project_root, "apps", "shared", "portelyra_ui_shell.R"), envir = shell_env)
    shell_env$pl_error_text_v1(code)
  }, error = function(error) NULL)
  if (is.character(text) && length(text) == 1L && nzchar(text)) text else paste0("Portelyra meldet: ", code)
}
# Meldet einen Abbruch auch als Hinweis, dann wie safe_main.
notify_failure <- function(expression, title) {
  tryCatch(force(expression), error = function(error) {
    code <- tryCatch(as.character(error$code), error = function(e) character())
    if (length(code) == 1L) portelyra_notify(title, portelyra_error_text(code))
    stop(error)
  })
}

# Zugang je Oeffnen (#570, rc.433): Jedes Oeffnen bekommt einen neuen Zugang; access.json im Sperrordner fuehrt nur dessen Fingerabdruck
# (und die abgeloesten), nie den Zugang. Geprueft wird in apps/shared/desktop_protection_v1.R (desktop_access_check_v1). Ohne Sperrordner
# (kein laufender Start) bleibt alles beim festen Token. Gibt TRUE zurueck, wenn die Datei geschrieben ist.
portelyra_access_file <- function() file.path(home, "desktop-session.lock", "access.json")
portelyra_access_issue <- function(token) {
  file <- portelyra_access_file()
  if (!dir.exists(dirname(file)) || .desktop_product_symlink_v1(file)) return(invisible(FALSE))
  previous <- if (file.exists(file)) tryCatch(jsonlite::fromJSON(file, simplifyVector = TRUE), error = function(error) NULL) else NULL
  retired <- as.character(unique(c(if (is.list(previous) && is.character(previous$current)) previous$current,
                                    if (is.list(previous)) as.character(unlist(previous$retired)))))   # nie NULL: I(NULL) scheitert
  value <- list(contract_version = 1L, current = digest::digest(enc2utf8(token), algo = "sha256", serialize = FALSE),
                retired = I(utils::head(retired, 50L)),
                issued_at_utc = format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
  temporary <- paste0(file, ".tmp-", Sys.getpid())
  writeLines(as.character(jsonlite::toJSON(value, auto_unbox = TRUE)), temporary)
  Sys.chmod(temporary, mode = "0600")
  if (!file.rename(temporary, file)) { unlink(temporary); return(invisible(FALSE)) }
  Sys.setenv(PORTELYRA_ACCESS_FILE_INTERNAL = file)
  invisible(TRUE)
}

# Zweiter Start, waehrend Portelyra laeuft (#570, rc.433). Statt still mit session_conflict
# abzubrechen, bittet der zweite Aufruf den laufenden Start, den Browser wieder zu oeffnen - auch die Entsperrseite oder den
# Einrichtungsdialog, je nachdem, wo er steht. Die Bitte ist eine Datei im Home (nur fuer den Eigentuemer). Den Zugang kennt nur der laufende
# Start; er oeffnet den Browser selbst wie beim Start und gibt ihn nie heraus. Ergebnis: "reopened" (bedient), "reopen_pending" (startet
# noch, wird bedient, sobald bereit) oder NULL (laeuft nicht, ist kein Start, oder beendet sich gerade - dann nach dem Ende normal starten).
portelyra_reopen_request_path <- function() file.path(home, "desktop-reopen-request.json")
portelyra_session_owner <- function() {
  owner_path <- file.path(home, "desktop-session.lock", "owner.json")
  owner <- if (!file.exists(owner_path) || .desktop_product_symlink_v1(owner_path)) NULL else
    tryCatch(jsonlite::fromJSON(owner_path, simplifyVector = FALSE), error = function(error) NULL)
  if (.desktop_product_lock_active_v1(owner)) owner else NULL
}
portelyra_reopen_running <- function(wait_seconds = 15) {
  owner <- portelyra_session_owner()
  if (is.null(owner) || !grepl("--file=.*portelyra_desktop[.]R --args start( |$)", process_command(as.character(as.integer(owner$pid))))) return(NULL)
  stopping <- file.path(home, "desktop-session.lock", "stopping")
  if (file.exists(stopping)) {
    deadline <- Sys.time() + 120
    while (!is.null(portelyra_session_owner()) && Sys.time() < deadline) Sys.sleep(0.5)
    return(NULL)
  }
  request <- portelyra_reopen_request_path()
  if (.desktop_product_symlink_v1(request) || dir.exists(request)) .desktop_product_abort_v1("desktop_product_symlink_rejected")
  old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
  stamp <- format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  writeLines(as.character(jsonlite::toJSON(list(contract_version = 1L, requested_at_utc = stamp), auto_unbox = TRUE)), request)
  deadline <- Sys.time() + wait_seconds
  repeat {
    if (!file.exists(request)) return(list(status = "reopened"))
    if (is.null(portelyra_session_owner())) { unlink(request, force = TRUE); return(NULL) }
    if (file.exists(stopping)) {
      unlink(request, force = TRUE)
      while (!is.null(portelyra_session_owner()) && Sys.time() < deadline + 120) Sys.sleep(0.5)
      return(NULL)
    }
    if (Sys.time() > deadline) return(list(status = "reopen_pending"))
    Sys.sleep(0.25)
  }
}
# Im laufenden Start: eine Bitte bedienen (aus den Warteschleifen von Apps, Entsperrseite und Einrichtungsdialog).
portelyra_reopen_serve <- function(open) {
  request <- portelyra_reopen_request_path()
  if (!file.exists(request) || dir.exists(request) || .desktop_product_symlink_v1(request)) return(invisible(FALSE))
  unlink(request, force = TRUE)
  tryCatch(open(), error = function(error) NULL)
  emit(list(status = "reopen_served"))
  invisible(TRUE)
}

# Update in einem Befehl (#489, rc.429; Festlegung 13.11.2026). `update --archive` fuehrt die erprobte Kette selbst aus,
# nur aus dem INSTALLIERTEN Portelyra (#486 Schritt 3):
#   1. Archiv pruefen (Pruefsummen, Signatur gegen die installierte Vertrauensliste) - schon eingespielt oder nicht neuer: nichts tun.
#   2. Wartungssperre (laeuft „Alles aktualisieren“, Abbruch mit Grund), laufendes Portelyra ruhig beenden: Arbeitet eine App gerade
#      (ein Kindprozess einer App, etwa eine Buchung oder ein Import), Abbruch mit desktop_product_update_busy - beendet wird dann nichts.
#   3. Mit Passwortschutz entsperren: Schluesselbund oder Startseite im Browser, nie ein Passwort auf der Befehlszeile.
#   4. Backup samt Pruefung durch das installierte Programm (Version des laufenden Stands, Name vor-<neue Version>-<Zeit>).
#   5. Upgrade, dann Preflight mit dem neuen Stand; scheitert er, nennt die Meldung den Rueckweg `rollback`.
#   6. Die drei juengsten gueltigen Backups dieses Datenraums behalten (Plan, dann genau dieser Plan), dann starten.
# Je Schritt eine Zeile `update_step`; die letzte Zeile ist `updated` (oder `already_current`) bzw. `blocked` mit dem Schritt. Scheitert
# es nach dem Beenden, aber vor dem Upgrade, startet Portelyra wieder mit dem bisherigen Stand (`restarted`). --no-start nur fuer Tests.
# Fortschrittsseite des Updates als eigener Prozess (#562 Paket 4): `update --page` startet sie mit dem Pfad ihrer Fortschrittsdatei und
# ihrem Port (Data-Port + 4). Sie endet von selbst, wenn nach dem Ergebnis die Nachlaufzeit vorbei ist (PORTELYRA_UPDATE_PAGE_LINGER_INTERNAL
# kuerzt sie nur fuer Tests), spaetestens nach 90 Minuten.
if (identical(command, "update-page")) {
  if (!all(c("progress", "port") %in% names(options)) || length(setdiff(names(options), c("no_browser", "progress", "port", "browser")))) {
    safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  }
  page <- page_options(options[intersect(names(options), c("no_browser", "port", "browser"))])
  page_main <- function() {
    page_env <- new.env(parent = globalenv())
    for (file in c("portelyra_ui_shell.R", "desktop_protection_v1.R", "desktop_update_page_v1.R"))
      sys.source(file.path(project_root, "apps", "shared", file), envir = page_env)
    linger <- suppressWarnings(as.numeric(Sys.getenv("PORTELYRA_UPDATE_PAGE_LINGER_INTERNAL", unset = "600")))
    if (length(linger) != 1L || is.na(linger) || linger < 1 || linger > 3600) linger <- 600
    opener <- if (isTRUE(options$no_browser)) function(url) message("Fortschritt des Updates im Browser: ", url) else page_opener(options, page)
    page_env$desktop_update_page_blocking_v1(options$progress, page$port, opener, page_env$portelyra_ui_css(), page_token_new(),
                                             linger_ms = linger * 1000)
    list(status = "update_page_closed")
  }
  safe_main(emit(page_main()))
  quit(save = "no", status = 0L)
}

# Archiv pruefen wie Schritt 1 von `update`, ohne etwas einzuspielen (#562 Paket 4): Signatur gegen die installierte Vertrauensliste,
# Versionen, neuer oder nicht. Data prueft so ein heruntergeladenes Update, bevor es „Update jetzt einspielen“ anbietet. Nur aus dem
# installierten Portelyra (wie `update`).
if (identical(command, "update-check")) {
  if (!identical(sort(names(options)), sort(c("no_browser", "archive"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  check_main <- function() {
    staged <- desktop_product_update_stage_v1(project_root, home, options$archive)
    on.exit(desktop_product_update_unstage_v1(staged), add = TRUE)
    list(status = "checked", product_version = staged$product_version, installed_version = staged$installed_version,
         signature = staged$signature, newer = isTRUE(staged$newer), already_current = isTRUE(staged$already_current))
  }
  safe_main(emit(check_main()))
  quit(save = "no", status = 0L)
}

if (identical(command, "update")) {
  if (!all(c("confirm", "archive") %in% names(options)) ||
      length(setdiff(names(options), c("no_browser", "confirm", "archive", "port", "browser", "no_start", "page")))) {
    safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  }
  if (!identical(options$confirm, "UPGRADE_LOCAL_RUNTIME")) safe_main(.desktop_product_abort_v1("desktop_product_upgrade_confirmation_required"))
  page <- page_options(options[intersect(names(options), c("no_browser", "port", "browser"))])
  rscript <- file.path(R.home("bin"), "Rscript")
  # Fortschrittsseite (#562 Paket 4): Mit --page laeuft eine eigene Seite (apps/shared/desktop_update_page_v1.R) auf dem Data-Port + 4 in
  # einem Kindprozess; dieses Update schreibt seinen Stand in eine Datei (0600), die Seite liest sie. Ohne Browser nennt das Terminal die
  # Adresse. Data startet das Update so, nachdem Sie „Update jetzt einspielen“ bestaetigt haben.
  update_page <- new.env()
  update_page$path <- NULL; update_page$steps <- list(); update_page$current <- "check"; update_page$outcome <- NULL
  update_page$from <- NULL; update_page$to <- NULL; update_page$log <- NULL
  page_write <- function() if (!is.null(update_page$path)) invisible(update_page$write(update_page$path, list(
    from_version = update_page$from, to_version = update_page$to, current = update_page$current, steps = update_page$steps,
    outcome = update_page$outcome, log = update_page$log)))
  page_enter <- function(step) { update_page$current <- step; page_write(); step }
  say <- function(step, ...) {
    line <- c(list(status = "update_step", step = step), list(...))
    emit(line)
    if (!is.null(update_page$path)) { update_page$steps[[length(update_page$steps) + 1L]] <- line; page_write() }
  }
  if (isTRUE(options$page)) local({
    page_port <- page$port + 4L
    probe <- if (page_port <= 65532L) tryCatch(suppressWarnings(socketConnection(host = "127.0.0.1", port = page_port, open = "r+b",
                                                                              blocking = TRUE, timeout = 0.2)), error = function(error) NULL) else NULL
    if (!is.null(probe)) close(probe)
    if (page_port > 65532L || !is.null(probe)) return(emit(list(status = "update_page", result = "port_busy")))
    state_root <- Sys.getenv("XDG_STATE_HOME", unset = "")
    if (!nzchar(state_root)) state_root <- file.path(path.expand("~"), ".local", "state")
    log_dir <- file.path(state_root, "portelyra")
    old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
    if (!dir.exists(log_dir)) dir.create(log_dir, recursive = TRUE, mode = "0700")
    page_env <- new.env(parent = globalenv())
    sys.source(file.path(project_root, "apps", "shared", "desktop_update_page_v1.R"), envir = page_env)
    update_page$write <- page_env$desktop_update_progress_write_v1
    update_page$path <- file.path(log_dir, paste0("update-progress-", Sys.getpid(), ".json"))
    update_page$log <- "~/.local/state/portelyra/update-<version>.log"
    page_write()
    # Ein eigener Prozess mit eigener Ausgabe (update-page): Als Kindprozess hielte die Seite die Ausgabe dieses Updates offen, und wer auf
    # deren Ende wartet (Terminal, Werkzeuge), wartete auf die Seite. Sie erzeugt ihr Start-Token selbst und oeffnet den Browser selbst.
    arguments <- c("--vanilla", file.path(project_root, "scripts", "portelyra_desktop.R"), "update-page", "--progress", update_page$path,
                   "--port", as.character(page_port),
                   if (isTRUE(options$no_browser)) "--no-browser" else if (!is.null(options$browser)) c("--browser", options$browser))
    page_log <- file.path(log_dir, "update-page.log")
    system2(file.path(R.home("bin"), "Rscript"), shQuote(arguments), stdout = page_log, stderr = page_log, stdin = "/dev/null", wait = FALSE)
    emit(list(status = "update_page", result = "started", port = page_port))
  })
  update_fail <- function(code) stop(structure(class = c("portelyra_update_error_v1", "error", "condition"),
                                               list(message = code, call = NULL, code = code)))
  last_json <- function(lines) {
    lines <- lines[nzchar(trimws(lines))]
    if (!length(lines)) return(NULL)
    tryCatch(jsonlite::fromJSON(lines[[length(lines)]], simplifyVector = FALSE), error = function(error) NULL)
  }
  stop_running <- function() portelyra_stop_running(update_fail)

  # Schritt 3: wie `unlock`, aber mit --no-browser nur ueber den Schluesselbund (eine Seite ohne Browser wartete endlos).
  unlock_if_locked <- function() {
    paths <- .desktop_product_home_paths_v1(home)
    if (!isTRUE(paths$protected)) return("not_protected")
    if (!isTRUE(paths$locked)) return("already_unlocked")
    session_lock <- file.path(home, "desktop-session.lock")
    session_owner <- .desktop_product_acquire_lock_v1(session_lock, "desktop_product_session_conflict")
    on.exit(if (dir.exists(session_lock)) .desktop_product_release_lock_v1(session_lock, session_owner), add = TRUE)
    protection_quarantine_requested(project_root, home)   # #568: noch gesperrt
    if (isTRUE(options$no_browser)) {
      protection_env <- new.env(parent = globalenv())
      sys.source(file.path(project_root, "apps", "shared", "desktop_protection_v1.R"), envir = protection_env)
      keyring <- protection_env$desktop_protection_cli_v1(project_root, home, "unlock-keyring")
      if (!identical(keyring$status, "completed") || !isTRUE(keyring$result$unlocked)) update_fail("desktop_product_locked")
    } else {
      status <- protection_unlock_page(project_root, home, paths$library, page$port, page_opener(options, page))
      if (!isTRUE(status$result$unlocked)) update_fail("desktop_product_locked")
    }
    "unlocked"
  }
  # Schritt 4: in den Backup-Ordner von Portelyra (mit Schutz den verschluesselten), dann vollstaendig pruefen.
  backup_before <- function(version) {
    if (!file.exists(.desktop_product_home_paths_v1(home)$registry)) return(list(result = "skipped_not_initialized"))
    backups_env <- new.env(parent = globalenv())
    sys.source(file.path(project_root, "apps", "shared", "desktop_protection_v1.R"), envir = backups_env)
    sys.source(file.path(project_root, "apps", "shared", "desktop_backups_v1.R"), envir = backups_env)
    root <- backups_env$desktop_backups_root_v1(project_root, home)
    if (!identical(root$status, "ready")) update_fail(if (is.character(root$code)) root$code else "desktop_release_boundary_failed")
    old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
    if (!dir.exists(root$root)) dir.create(root$root, recursive = TRUE, mode = "0700")
    name <- paste0("vor-", version, "-", format(Sys.time(), "%Y%m%d-%H%M%S"))
    created <- desktop_release_backup_v1(project_root, home, file.path(root$root, name), "CREATE_OWNER_BACKUP")
    if (!identical(created$status, "created")) update_fail("desktop_release_boundary_failed")
    checked <- desktop_release_backup_check_v1(project_root, file.path(root$root, name))
    if (!identical(checked$status, "valid")) update_fail("desktop_release_backup_integrity_invalid")
    list(result = "created", name = name, root = root$root, product_version = checked$product_version,
         file_count = checked$file_count, byte_count = checked$byte_count)
  }
  # Ab Schritt 5 laeuft der neue Stand als eigener Prozess: Diese Sitzung hat noch den alten Code geladen.
  run_installed <- function(...) {
    script <- file.path(.desktop_product_active_source_v1(home), "scripts", "portelyra_desktop.R")
    last_json(suppressWarnings(system2(rscript, shQuote(c(script, ...)), stdout = TRUE, stderr = FALSE)))
  }
  # Schritt 6 (und Neustart des bisherigen Stands): abgekoppelt starten, ab 0.3.3 in einer eigenen Einheit der Sitzung (#588, siehe
  # .desktop_product_app_unit_v1), Ausgabe nach $XDG_STATE_HOME/portelyra/start-<version>.log; fertig, sobald die Data-App antwortet
  # (hoechstens zwei Minuten). Ergebnis: result ("started", "not_confirmed"), unit ("own", "none") und ohne Einheit deren Grund.
  start_detached <- function(version) {
    setsid <- Sys.which("setsid")
    if (!nzchar(setsid)) return(list(result = "not_confirmed", unit = "none", unit_reason = "setsid_missing"))
    state_root <- Sys.getenv("XDG_STATE_HOME", unset = "")
    if (!nzchar(state_root)) state_root <- file.path(path.expand("~"), ".local", "state")
    old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
    log_dir <- file.path(state_root, "portelyra")
    if (!dir.exists(log_dir)) dir.create(log_dir, recursive = TRUE, mode = "0700")
    script <- file.path(.desktop_product_active_source_v1(home), "scripts", "portelyra_desktop.R")
    arguments <- c(script, "start", "--port", as.character(page$port),
                   if (isTRUE(options$no_browser)) "--no-browser" else if (!is.null(options$browser)) c("--browser", options$browser))
    log <- file.path(log_dir, paste0("start-", version, ".log"))
    unit <- .desktop_product_app_unit_v1(home)
    placement <- c(list(unit = if (is.null(unit$unit)) "none" else "own"), if (!is.null(unit$reason)) list(unit_reason = unit$reason))
    system2(setsid, c("-f", shQuote(unit$prefix), shQuote(rscript), shQuote(arguments)), stdout = log, stderr = log, stdin = "/dev/null", wait = FALSE)
    for (attempt in seq_len(600L)) {
      connection <- tryCatch(suppressWarnings(socketConnection(host = "127.0.0.1", port = page$port, open = "r+b", blocking = TRUE, timeout = 0.2)),
                             error = function(error) NULL)
      if (!is.null(connection)) { close(connection); return(c(list(result = "started"), placement)) }
      Sys.sleep(0.2)
    }
    c(list(result = "not_confirmed"), placement)
  }

  update_product <- function() {
    progress <- new.env()
    progress$step <- "check"; progress$stopped <- FALSE; progress$upgraded <- FALSE
    progress$resume <- function() invisible(NULL); progress$paused <- FALSE; progress$staged <- NULL
    cleanup <- function() {
      progress$resume(); progress$resume <- function() invisible(NULL); progress$paused <- FALSE
      desktop_product_update_unstage_v1(progress$staged)
    }
    on.exit(cleanup(), add = TRUE)
    # Die Wartungssperre einmal: entsperrt vor dem Beenden, sonst nach dem Entsperren. Sie bleibt gueltig, wenn der Start beim Beenden
    # sperrt (die Sperrdateien liegen im Datenbestand, ein Begleitprozess erneuert sie).
    pause <- function() if (!progress$paused) {
      progress$resume <- refresh_pause(on_conflict = cleanup); progress$paused <- TRUE
    }
    outcome <- tryCatch({
      staged <- desktop_product_update_stage_v1(project_root, home, options$archive)
      progress$staged <- staged
      update_page$from <- staged$installed_version; update_page$to <- staged$product_version
      say("check", result = "valid", signature = staged$signature, product_version = staged$product_version,
          installed_version = staged$installed_version)
      if (isTRUE(staged$already_current)) return(list(status = "already_current", product_version = staged$installed_version))
      if (!isTRUE(staged$newer)) update_fail("desktop_product_upgrade_unavailable")

      progress$step <- page_enter("stop")
      paths <- .desktop_product_home_paths_v1(home)
      if (!isTRUE(paths$locked)) pause()
      progress$stopped <- stop_running()
      say("stop", result = if (progress$stopped) "stopped" else "not_running")

      progress$step <- page_enter("unlock")
      unlocked <- unlock_if_locked()
      say("unlock", result = unlocked)
      pause()

      progress$step <- page_enter("backup")
      backup <- backup_before(staged$product_version)
      say("backup", result = backup$result, name = backup$name, product_version = backup$product_version, file_count = backup$file_count)

      progress$step <- page_enter("upgrade")
      upgraded <- .desktop_product_upgrade_impl_v1(staged$candidate, home, options$confirm, fail_at = "none", candidate_scope = "own")
      progress$upgraded <- TRUE
      desktop_product_update_unstage_v1(staged)
      say("upgrade", result = upgraded$status, product_version = upgraded$product_version)

      progress$step <- page_enter("preflight")
      preflight <- run_installed("preflight")
      initialized <- file.exists(.desktop_product_home_paths_v1(home)$registry)
      expected <- if (initialized) "ready_to_start" else "ready_to_initialize"
      if (!is.list(preflight) || !identical(preflight$status, expected)) update_fail("desktop_product_update_preflight_failed")
      say("preflight", result = preflight$status)

      progress$step <- page_enter("prune")
      pruned <- if (identical(backup$result, "created")) {
        plan <- run_installed("backup-prune", "--root", backup$root, "--keep", "3")
        if (!is.list(plan) || !identical(plan$status, "planned")) list(result = "skipped", removed = 0L)
        else if (!length(plan$removed)) list(result = "nothing_to_remove", removed = 0L)
        else {
          done <- run_installed("backup-prune", "--root", backup$root, "--keep", "3", "--plan", plan$plan_fingerprint, "--confirm", "PRUNE_OWNER_BACKUPS")
          if (is.list(done) && identical(done$status, "pruned")) list(result = "pruned", removed = length(done$removed)) else list(result = "failed", removed = 0L)
        }
      } else list(result = "skipped", removed = 0L)
      say("prune", result = pruned$result, removed = pruned$removed)
      cleanup()

      progress$step <- page_enter("start")
      started <- if (isTRUE(options$no_start)) list(result = "skipped") else start_detached(upgraded$product_version)
      do.call(say, c(list("start"), started))
      list(status = "updated", product_version = upgraded$product_version, previous_version = staged$installed_version,
           signature = staged$signature, backup = backup$name, backup_product_version = backup$product_version,
           pruned = pruned$removed, start = started$result)
    }, error = function(error) error)
    if (!inherits(outcome, "error")) return(outcome)
    cleanup()
    code <- tryCatch(as.character(outcome$code), error = function(error) character())
    if (length(code) != 1L || !grepl("^desktop_", code)) code <- "desktop_product_boundary_failed"
    restarted <- if (progress$stopped && !progress$upgraded && !isTRUE(options$no_start)) {
      tryCatch(start_detached(if (is.list(progress$staged)) progress$staged$installed_version else "bisher")$result, error = function(error) "not_confirmed")
    } else NULL
    shown <- tryCatch(outcome$relative_path, error = function(error) NULL)   # #568
    update_page$outcome <- c(list(status = "blocked", code = code, step = progress$step), if (!is.null(restarted)) list(restarted = restarted),
                             if (progress$upgraded) list(rollback = "rollback --confirm ROLLBACK_LOCAL_RUNTIME"))
    page_write()
    emit(c(list(status = "blocked", code = code, step = progress$step),
           if (!is.null(restarted)) list(restarted = restarted),
           if (progress$upgraded) list(rollback = "rollback --confirm ROLLBACK_LOCAL_RUNTIME"),
           if (is.character(shown) && length(shown) == 1L) list(relative_path = shown)))
    quit(save = "no", status = 2L)
  }
  result <- safe_main(update_product())
  update_page$outcome <- result; page_write()
  emit(result)
  quit(save = "no", status = 0L)
}

# Portelyra beenden (#489, rc.431): fuer den Starter ohne Terminal (Aktion „Portelyra beenden“) und fuer Werkzeuge. Wie beim Update:
# nur ein Start dieses Homes, nicht mitten in einer Buchung (desktop_product_update_busy); SIGINT, dann warten, bis Start und Apps beendet
# sind. Mit Passwortschutz sperrt der Start dabei den Datenbestand.
if (identical(command, "stop")) {
  if (length(setdiff(names(options), c("no_browser", "notify"))) || isTRUE(options$no_browser)) safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  stop_fail <- function(code) stop(structure(class = c("portelyra_stop_error_v1", "error", "condition"), list(message = code, call = NULL, code = code)))
  stopped <- tryCatch(portelyra_stop_running(stop_fail), error = function(error) error)
  if (inherits(stopped, "error")) {
    code <- tryCatch(as.character(stopped$code), error = function(error) character())
    code <- if (length(code) == 1L && startsWith(code, "desktop_")) code else "desktop_product_boundary_failed"
    portelyra_notify(if (identical(code, "desktop_product_update_busy")) "Portelyra arbeitet gerade" else "Portelyra beendet sich nicht",
                     portelyra_error_text(code))
    emit(list(status = "blocked", code = code))
    quit(save = "no", status = 2L)
  }
  portelyra_notify(if (isTRUE(stopped)) "Portelyra ist beendet" else "Portelyra läuft nicht",
                   if (isTRUE(stopped)) "Zeitpläne laufen weiter." else "")
  emit(list(status = if (isTRUE(stopped)) "stopped" else "not_running"))
  quit(save = "no", status = 0L)
}

# Starter (#489, rc.431): ein Eintrag im Anwendungsmenue, damit nach der Installation kein Terminal mehr noetig ist. Nur aus dem installierten
# Portelyra: Der Eintrag ruft dessen Start auf, und das ist nach jedem Update der neue Stand (seit rc.429 startet er ohne Projektordner).
# Zweite Aktion „Portelyra beenden“ (`stop`). Ein abweichendes PORTELYRA_DESKTOP_HOME geht in den Eintrag mit. Ueberschreibt nur den eigenen
# Eintrag portelyra.desktop. Seit 0.3.3 (#586) steht der Browser nicht mehr in der Zeile Exec: --browser legt ihn in den Einstellungen der
# Installation fest (wie der Reiter „Programm“); der Starter liest ihn bei jedem Oeffnen.
if (identical(command, "desktop-entry")) {
  if (!identical(options$confirm, "CREATE_DESKTOP_ENTRY") || isTRUE(options$no_browser) ||
      length(setdiff(names(options), c("no_browser", "confirm", "browser"))) ||
      (!is.null(options$browser) && !options$browser %in% DESKTOP_BROWSER_NAMES_V1)) {
    safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
  }
  entry_main <- function() {
    active <- tryCatch(.desktop_product_active_source_v1(home), error = function(error) NULL)
    if (is.null(active) || !identical(.desktop_product_normalize_existing_v1(project_root), active)) .desktop_release_abort_v1("desktop_release_update_entry_untrusted")
    # Ein genannter Browser muss gefunden werden (sonst desktop_product_dependency_missing), bevor etwas geschrieben wird.
    chosen <- if (is.null(options$browser)) NULL else desktop_browser_resolve_v1(home, options$browser)$name
    if (!is.null(chosen)) desktop_installation_settings_write_v1(home, list(browser = chosen))
    data_home <- Sys.getenv("XDG_DATA_HOME", unset = "")
    if (!nzchar(data_home)) data_home <- file.path(path.expand("~"), ".local", "share")
    applications <- file.path(data_home, "applications")
    if (!dir.exists(applications)) dir.create(applications, recursive = TRUE, mode = "0755")
    quoted <- .desktop_product_entry_quote_v1   # Exec nach der Desktop-Entry-Spezifikation
    # Bildmarke (#584): als Symbol "portelyra" ins Symbolthema; fehlt sie, bleibt das allgemeine Symbol.
    icon <- if (isTRUE(tryCatch(.desktop_product_icon_install_v1(active, data_home), error = function(error) FALSE))) "portelyra" else "applications-office"
    script <- file.path(active, "scripts", "portelyra_desktop.R")
    prefix <- c(if (nzchar(Sys.getenv("PORTELYRA_DESKTOP_HOME", unset = ""))) c("env", quoted(paste0("PORTELYRA_DESKTOP_HOME=", home))),
                quoted(file.path(R.home("bin"), "Rscript")), quoted(script))
    content <- c(
      "[Desktop Entry]", "Type=Application", "Version=1.5", "Name=Portelyra", "GenericName=Portfolio und Steuer",
      "Comment=Portfolio, Kurse und Steuer – lokal auf diesem Rechner",
      paste0("Exec=", paste(c(prefix, "start", "--notify"), collapse = " ")),
      paste0("Icon=", icon), "Terminal=false", "StartupNotify=false", "Categories=Office;Finance;", "Actions=beenden;",
      "", "[Desktop Action beenden]", "Name=Portelyra beenden", paste0("Exec=", paste(c(prefix, "stop", "--notify"), collapse = " ")), "")
    target <- file.path(applications, "portelyra.desktop")
    if (.desktop_product_symlink_v1(target)) .desktop_product_abort_v1("desktop_product_symlink_rejected")
    temporary <- paste0(target, ".tmp-", Sys.getpid())
    writeLines(enc2utf8(content), temporary, useBytes = TRUE)
    Sys.chmod(temporary, mode = "0644")
    if (!file.rename(temporary, target)) { unlink(temporary); .desktop_product_abort_v1("desktop_product_boundary_failed") }
    c(list(status = "created", entry = "portelyra.desktop", actions = list("start", "stop"), icon = icon), if (!is.null(chosen)) list(browser = chosen))
  }
  safe_main(emit(entry_main()))
  quit(save = "no", status = 0L)
}

# Nur entsperren, ohne die Apps zu starten (#535): etwa vor Backup und Upgrade, die den entsperrten Bestand brauchen. Gesperrt wird
# beim naechsten Beenden von Portelyra oder mit dem Kern (desktop_protection.py lock).
if (identical(command, "unlock")) {
  page <- page_options(options)
  unlock_only <- function() {
    paths <- .desktop_product_home_paths_v1(home)
    if (!isTRUE(paths$protected)) return(emit(list(status = "not_protected")))
    if (!isTRUE(paths$locked)) return(emit(list(status = "unlocked")))
    session_lock <- file.path(home, "desktop-session.lock")
    session_owner <- .desktop_product_acquire_lock_v1(session_lock, "desktop_product_session_conflict")
    on.exit(if (dir.exists(session_lock)) .desktop_product_release_lock_v1(session_lock, session_owner), add = TRUE)
    protection_quarantine_requested(.desktop_product_active_source_v1(home), home)   # #568: noch gesperrt
    status <- protection_unlock_page(.desktop_product_active_source_v1(home), home, paths$library, page$port, page_opener(options, page))
    if (!isTRUE(status$result$unlocked)) .desktop_product_abort_v1("desktop_product_locked")
    emit(list(status = "unlocked"))
  }
  safe_main(unlock_only())
  quit(save = "no", status = 0L)
}

if (identical(command, "start")) {
  page <- page_options(options, setup = TRUE)
  port <- page$port
  start_product <- function() {
    start_ready <- function(value) value$status %in% c("ready_to_start", "upgrade_required") &&
      isTRUE(value$checks$local_packages_installed) && isTRUE(value$checks$runtime_registry_initialized) &&
      !isTRUE(value$checks$upgrade_recovery_required)
    preflight <- desktop_product_preflight_v1(project_root, home)
    if (!start_ready(preflight)) .desktop_product_abort_v1("desktop_product_not_initialized")
    active_root <- .desktop_product_active_source_v1(home)
    session_lock <- file.path(home, "desktop-session.lock")
    # #570: Laeuft Portelyra schon, oeffnet der laufende Start den Browser wieder; dieser Aufruf endet dann.
    reopened <- portelyra_reopen_running()
    if (!is.null(reopened)) {
      if (identical(reopened$status, "reopened")) portelyra_notify("Portelyra läuft bereits", "Portelyra ist wieder geöffnet.")
      else portelyra_notify("Portelyra startet gerade", "Es öffnet sich, sobald es bereit ist.")
      return(reopened)
    }
    # Starter von vor 0.3.3 bekommen hier die Bildmarke (#584), auch nach einem Update, das noch der Code des alten Stands ausfuehrte.
    entry_icon <- tryCatch(.desktop_product_entry_icon_refresh_v1(active_root), error = function(error) "failed")
    if (identical(entry_icon, "updated")) emit(list(status = "desktop_entry_icon", result = "updated"))
    # Ebenso der Browser (#586): `--browser <name>` aus der Zeile Exec wandert in die Einstellungen der Installation, sonst ginge die
    # Kommandozeile des Starters jeder Wahl im Reiter „Programm“ vor. Gilt ab dem naechsten Oeffnen; dieser Start behaelt seine Wahl.
    entry_browser <- tryCatch(desktop_installation_entry_browser_migrate_v1(active_root, home), error = function(error) "failed")
    if (entry_browser %in% c("moved", "removed", "failed")) emit(list(status = "desktop_entry_browser", result = entry_browser))
    portelyra_notify("Portelyra startet …", "Der Browser öffnet sich, sobald Portelyra bereit ist.")
    session_owner <- .desktop_product_acquire_lock_v1(session_lock, "desktop_product_session_conflict")
    # Die Sitzungssperre gilt bis zuletzt (#570, rc.433): Bis rc.432 gab der Start sie beim Beenden als Erstes frei und hielt erst danach die
    # Apps an und sperrte den Bestand - ein neuer Start konnte hineinlaufen. Bricht der Start frueh ab, gibt sie dieser Handler frei; sobald die
    # Apps laufen, uebernimmt der letzte Handler (unten, nach Anhalten und Sperren).
    release_early <- TRUE
    on.exit(if (release_early && dir.exists(session_lock)) .desktop_product_release_lock_v1(session_lock, session_owner), add = TRUE)
    # Beim Beenden zuerst vermerken, dass Portelyra sich beendet: Ein Klick auf den Starter wartet dann und startet danach neu (#570).
    on.exit(if (dir.exists(session_lock)) try(writeLines("stopping", file.path(session_lock, "stopping")), silent = TRUE), add = TRUE, after = FALSE)
    unlink(portelyra_reopen_request_path(), force = TRUE)                                 # eine liegengebliebene Bitte gilt nicht
    preflight <- desktop_product_preflight_v1(project_root, home)
    if (!start_ready(preflight)) .desktop_product_abort_v1("desktop_product_not_initialized")
    project_root <- active_root
    # Demo aus dem Einrichtungsdialog (#487 Teil 2, rc.413): Es hat kein eigenes Terminal und endet deshalb mit diesem Portelyra. Der
    # Dialog erfaehrt hier, mit welchem Browser gestartet wurde, damit das Demo denselben nimmt.
    Sys.setenv(PORTELYRA_BROWSER_NAME_INTERNAL = if (isTRUE(options$no_browser)) "none" else page_browser(page)$name)
    demo_helper <- file.path(project_root, "apps", "shared", "desktop_demo_home_v1.R")
    if (file.exists(demo_helper)) on.exit(tryCatch({
      demo_env <- new.env(parent = globalenv()); sys.source(demo_helper, envir = demo_env)
      demo_env$desktop_demo_home_stop_spawned_v1(home)
    }, error = function(error) NULL), add = TRUE)
    # Laeuft hier das Demo-Home (#487)? Dann fragt Data nicht nach der Update-Suche (#562): Das Demo ist keine Installation, die man
    # aktualisiert; es nutzt das Programm der eigenen. Erkannt am Ort, der dem Demo vorbehalten ist (desktop_demo_home_paths_v1).
    in_demo <- file.exists(demo_helper) && isTRUE(tryCatch({
      probe <- new.env(parent = globalenv()); sys.source(demo_helper, envir = probe)
      identical(normalizePath(home, winslash = "/", mustWork = FALSE),
                normalizePath(probe$desktop_demo_home_paths_v1()$home, winslash = "/", mustWork = FALSE))
    }, error = function(error) FALSE))
    # Passwortschutz (#535, rc.396): Gesperrt zeigt eine eigene Startseite auf dem Port der Data-App, bis entsperrt ist; danach starten die
    # Apps wie gewohnt. Ohne Schutz geht es sofort weiter. Der Bestand bleibt danach bis zur Abmeldung offen (#587); gesperrt wird beim
    # Beenden nur, wenn es eingestellt oder angefordert ist (unten, nach dem Anhalten der Apps).
    protection_paths <- .desktop_product_home_paths_v1(home)
    if (isTRUE(protection_paths$protected)) {
      # Schon entsperrt (etwa mit `unlock` vor einem Upgrade): keine Seite, gleich weiter.
      if (isTRUE(protection_paths$locked)) protection_quarantine_requested(project_root, home)   # #568: noch gesperrt
      unlocked <- protection_unlock_page(project_root, home, protection_paths$library, port, page_opener(options, page))
      if (!isTRUE(unlocked$result$unlocked)) .desktop_product_abort_v1("desktop_product_locked")
    }
    source(file.path(project_root, "packages", "spotcore", "R", "runtime_context.R"), local = .GlobalEnv)
    source(file.path(project_root, "packages", "spotcore", "R", "desktop_product_runtime_v1.R"), local = .GlobalEnv)
    source(file.path(project_root, "packages", "spotcore", "R", "desktop_release_v1.R"), local = .GlobalEnv)
    # Erster entsperrter Start nach dem Einrichten (#535): ein Backup im verschluesselten Backup-Ordner, bevor die Apps laufen - die
    # Data-App kann keine Backups anlegen, und der Klartext wird erst danach geloescht. Das Backup nimmt die Sitzungssperre selbst.
    first_backup_if_due <- function(result) {
      if (!isTRUE(result$first_backup_due) || !is.character(result$backups_root)) return(FALSE)
      target <- file.path(result$backups_root, paste0("nach-verschluesselung-", format(Sys.time(), "%Y%m%d-%H%M%S")))
      .desktop_product_release_lock_v1(session_lock, session_owner)
      first_backup <- tryCatch(desktop_release_backup_v1(project_root, home, target, "CREATE_OWNER_BACKUP"), error = function(error) error)
      session_owner <<- .desktop_product_acquire_lock_v1(session_lock, "desktop_product_session_conflict")
      emit(list(status = "protection_first_backup", result = if (inherits(first_backup, "error")) "failed" else first_backup$status,
                code = if (inherits(first_backup, "error")) tryCatch(as.character(first_backup$code), error = function(error) NULL)))
      !inherits(first_backup, "error") && identical(first_backup$status, "created")
    }
    if (isTRUE(protection_paths$protected)) {
      invisible(first_backup_if_due(unlocked$result))
      # Hat ein Zeitlauf gerade geoeffnet, gehoert der Bestand ab jetzt dem Benutzer: Das Laufende sperrt ihn nicht mehr (#587).
      invisible(tryCatch(desktop_protection_cli_v1(project_root, home, "keep-open"), error = function(error) NULL))
      # War schon entsperrt (ein Zeitlauf, ein frueherer Start), laeuft der Waechter fuer den Ruhezustand vielleicht noch nicht (#587).
      invisible(tryCatch(desktop_protection_cli_v1(project_root, home, "ensure-sleep-guard"), error = function(error) NULL))
      # Ein Zeitlauf, der ausfiel, weil nach dem Ruhezustand das Passwort fehlte, kommt jetzt (#587). Hier und nicht beim Entsperren:
      # `update` entsperrt vor Backup und Upgrade, und ein laufender Lauf blockierte beide.
      invisible(tryCatch(desktop_protection_cli_v1(project_root, home, "catch-up-after-sleep"), error = function(error) NULL))
    }
    runtime <- desktop_product_runtime_load_v1(home)
    .libPaths(c(runtime$library, .libPaths()))
    if (!requireNamespace("spotcore", quietly = TRUE) || !requireNamespace("spotdisplay", quietly = TRUE) ||
        !requireNamespace("shiny", quietly = TRUE)) .desktop_product_abort_v1("desktop_product_dependency_missing")
    # Einrichtungsdialog (#555): beim ersten Start (kein Datenraum) oder wenn ein Entwurf auf Fortsetzung wartet; danach die Laufzeit
    # neu lesen, denn der Dialog kann den Datenraum angelegt haben. An einem eingerichteten Home ohne Entwurf erscheint er nie.
    if (!isTRUE(options$skip_setup)) {
      setup <- setup_page(project_root, home, port, page_opener(options, page))
      if (isTRUE(setup$ran)) {
        emit(list(status = "setup", result = setup$state))
        # Hat der Dialog den Passwortschutz eingerichtet (#555 b), ist der Bestand schon eingehaengt: das erste Backup im verschluesselten
        # Ordner wie nach dem Einrichten in der Karte, danach - so in der Zusammenfassung bestaetigt - den unverschluesselten Bestand entfernen.
        if (isTRUE(setup$protection)) {
          if (!exists("desktop_protection_cli_v1", mode = "function")) source(file.path(project_root, "apps", "shared", "desktop_protection_v1.R"), local = .GlobalEnv)
          current <- desktop_protection_cli_v1(project_root, home, "status")
          # Nur entfernen, wenn der Schutz keine fremden Backups mitgenommen hat: finalize loescht die mitgenommenen Klartext-Backups. Der
          # Dialog nimmt keine mit (13.11.2026); steht doch ein Ordner im Zustand, bleibt der Klartext und das Entfernen geht ueber die Karte.
          recorded <- tryCatch(jsonlite::fromJSON(file.path(home, "protection.json"), simplifyVector = FALSE), error = function(error) NULL)
          own_only <- is.list(recorded) && is.null(recorded$plaintext_backups)
          if (identical(current$status, "completed") && isTRUE(current$result$unlocked) && isTRUE(first_backup_if_due(current$result))) {
            if (own_only) {
              finalized <- desktop_protection_cli_v1(project_root, home, "finalize", list(confirmed = TRUE))
              emit(list(status = "protection_plaintext_removed", result = finalized$status, code = finalized$code))
            } else emit(list(status = "protection_plaintext_kept", reason = "plaintext_backups_recorded"))
          }
        }
        # Beim Beenden sperren, auch wenn der Schutz erst im Dialog entstand.
        protection_paths <- .desktop_product_home_paths_v1(home)
        runtime <- desktop_product_runtime_load_v1(home)
      }
    }
    Sys.unsetenv(c(
      "PORTELYRA_APP_URL_DATA", "PORTELYRA_APP_URL_COCKPIT",
      "PORTELYRA_APP_URL_TAX", "PORTELYRA_APP_URL_ANALYSIS"
    ))
    Sys.setenv(
      PORTELYRA_DESKTOP_PROJECT_ROOT_INTERNAL = project_root,
      PORTELYRA_DESKTOP_HOME_INTERNAL = home,
      PYTHONDONTWRITEBYTECODE = "1"
    )
    app_names <- c("data", "cockpit", "tax", "analysis")
    app_ports <- stats::setNames(port + 0:3, app_names)
    launch_token <- paste0("dls_", paste(format(openssl::rand_bytes(32L)), collapse = ""))
    # #570: Pruefung je neuem Seitenaufruf gegen access.json (aktueller Zugang hinein, abgeloester nur Hinweis, sonst schliessen).
    access_env <- new.env(parent = globalenv())
    sys.source(file.path(project_root, "apps", "shared", "desktop_protection_v1.R"), envir = access_env)
    portelyra_access_issue(launch_token)
    secure_app <- function(app) {
      original_source <- app$serverFuncSource
      app$serverFuncSource <- local({
        source_function <- original_source
        function() {
          original_server <- source_function()
          function(input, output, session) {
            authorized <- FALSE
            shiny::observe({
              search <- session$clientData$url_search
              shiny::req(is.character(search), length(search) == 1L, !is.na(search))
              shiny::isolate(if (!authorized) {
                authorized <<- TRUE
                access_env$desktop_access_gate_v1(access_env$desktop_access_check_v1(search, launch_token), session, function() {
                  # Bestand weg bei laufender App (#587): sofort sagen und nichts mehr ins Leere schreiben.
                  if (isTRUE(protection_paths$protected)) access_env$desktop_protection_guard_v1(session, project_root, home, protection_paths$data_root)
                  original_server(input, output, session)
                }, search)
              })
            })
          }
        }
      })
      app
    }
    base::options(portelyra.desktop.project_root = project_root, portelyra.desktop.runtime = runtime,
                  portelyra.desktop.ports = app_ports, portelyra.desktop.demo = in_demo)
    apps <- lapply(app_names, function(app_name) {
      environment <- new.env(parent = globalenv())
      app <- source(file.path(project_root, "apps", app_name, "desktop_product_app_v1.R"), local = environment, chdir = FALSE)$value
      secure_app(app)
    })
    names(apps) <- app_names
    jobs <- lapply(app_names, function(app_name) parallel::mcparallel({
      shiny::runApp(apps[[app_name]], host = "127.0.0.1", port = app_ports[[app_name]],
                    launch.browser = FALSE, quiet = TRUE)
    }, silent = TRUE))
    on.exit({
      for (job in jobs) try(tools::pskill(job$pid), silent = TRUE)
      try(parallel::mccollect(jobs, wait = FALSE), silent = TRUE)
      # Passwortschutz (#587): Der Bestand bleibt bis zur Abmeldung offen. Gesperrt wird nach dem Anhalten der Apps nur, wenn es eingestellt
      # oder angefordert ist oder ein Ablauf es braucht (Schluessel erneuern, Quarantaene, Klartext noch nicht entfernt).
      if (isTRUE(protection_paths$protected)) {
        Sys.sleep(1)
        locked <- tryCatch(desktop_protection_cli_v1(project_root, home, "lock-if-due"), error = function(error) NULL)
        # Haelt noch ein Hintergrundlauf eine Datei offen, bleibt entsperrt; der Lauf sperrt an seinem Ende selbst (desktop_refresh_all.R).
        if (!is.list(locked) || (isTRUE(locked$result$lock_due) && !identical(locked$result$unlocked, FALSE))) emit(list(status = "protection_lock_pending"))
      }
    }, add = TRUE)
    # Taegliche Update-Suche (#562 Paket 3): nur mit Zustimmung und hoechstens einmal am Tag, als Kindprozess im Hintergrund; das Ergebnis
    # steht danach in update-status.json, das alle Apps lesen. Erste Pruefung zwei Minuten nach dem Start, dann alle zehn Minuten - sie liest
    # nur zwei Dateien (desktop_update_due_v1); abgefragt wird erst, wenn die Suche faellig ist, und der Kern prueft das noch einmal.
    update_version <- tryCatch(trimws(readLines(file.path(project_root, "VERSION"), n = 1L, warn = FALSE)), error = function(error) "")
    update_job <- NULL
    update_next <- Sys.time() + 120
    update_tick <- function() {
      if (!is.null(update_job)) {
        if (!is.null(tryCatch(parallel::mccollect(update_job, wait = FALSE), error = function(error) TRUE))) update_job <<- NULL
        return(invisible(NULL))
      }
      if (Sys.time() < update_next) return(invisible(NULL))
      update_next <<- Sys.time() + 600
      if (!isTRUE(tryCatch(desktop_update_due_v1(home)$due, error = function(error) FALSE))) return(invisible(NULL))
      update_job <<- tryCatch(parallel::mcparallel(desktop_update_cli_v1(project_root, "check",
        list(home = home, running = update_version, trigger = "daily")), silent = TRUE), error = function(error) NULL)
      invisible(NULL)
    }
    on.exit(if (!is.null(update_job)) try(tools::pskill(update_job$pid), silent = TRUE), add = TRUE)
    release_early <- FALSE
    on.exit(if (dir.exists(session_lock)) .desktop_product_release_lock_v1(session_lock, session_owner), add = TRUE)   # zuletzt (#570)
    if (!isTRUE(options$no_browser)) {
      ready <- FALSE
      for (attempt in seq_len(120L)) {
        connection <- tryCatch(socketConnection(host="127.0.0.1",port=app_ports[["data"]],open="r+b",blocking=TRUE,timeout=.1),error=function(error)NULL)
        if (!is.null(connection)) {close(connection);ready<-TRUE;break}
        Sys.sleep(.1)
      }
      if (!ready) .desktop_product_abort_v1("desktop_product_boundary_failed")
      desktop_browser_open_v1(paste0("http://127.0.0.1:", app_ports[["data"]], "?launch_token=", launch_token), page_browser(page))
    } else page_url_say(paste0("http://127.0.0.1:", app_ports[["data"]], "?launch_token=", launch_token))
    emit(list(status = "starting", apps = app_names, ports = as.list(app_ports), transport = "loopback", launch_session = "required", provider_access = FALSE))
    # #570: Wiederoeffnen mit neuem Zugang; der vorige verfaellt (auch ohne Browser, damit ein alter Link nicht weiter gilt).
    open_apps <- function() {
      fresh <- paste0("dls_", paste(format(openssl::rand_bytes(32L)), collapse = ""))
      portelyra_access_issue(fresh)
      if (!isTRUE(options$no_browser)) {
        desktop_browser_open_v1(paste0("http://127.0.0.1:", app_ports[["data"]], "?launch_token=", fresh), page_browser(page))
      } else page_url_say(paste0("http://127.0.0.1:", app_ports[["data"]], "?launch_token=", fresh))
    }
    repeat {
      completed <- parallel::mccollect(jobs, wait = FALSE)
      if (length(completed)) .desktop_product_abort_v1("desktop_product_boundary_failed")
      portelyra_reopen_serve(open_apps)                                                  # #570: zweiter Klick auf den Starter
      update_tick()                                                                      # #562: taegliche Update-Suche
      Sys.sleep(0.25)
    }
  }
  result <- safe_main(notify_failure(start_product(), "Portelyra startet nicht"))
  if (is.list(result)) emit(result)
  quit(save = "no", status = 0L)
}

safe_main(stop("desktop_product_cli_input_invalid", call. = FALSE))
