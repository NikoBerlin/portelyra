desktop_release_error_codes_v1 <- function() {
  c(
    "desktop_release_acceptance_artifact_missing", "desktop_release_acceptance_failed",
    "desktop_release_backup_conflict", "desktop_release_backup_integrity_invalid",
    "desktop_release_backup_source_changed", "desktop_release_backup_target_unprotected", "desktop_release_boundary_failed",
    "desktop_release_confirmation_required", "desktop_release_context_mismatch",
    "desktop_release_input_invalid", "desktop_release_locked", "desktop_release_manifest_invalid",
    "desktop_release_permissions_invalid", "desktop_release_release_conflict",
    "desktop_release_release_integrity_invalid", "desktop_release_restore_conflict",
    "desktop_release_restore_context_mismatch", "desktop_release_restore_target_not_empty", "desktop_release_restore_newer_version",
    "desktop_release_root_invalid", "desktop_release_session_invalid",
    "desktop_release_signature_invalid", "desktop_release_signature_missing", "desktop_release_signature_tool_missing",
    "desktop_release_signature_untrusted", "desktop_release_signing_copy_unconfirmed", "desktop_release_signing_declined", "desktop_release_signing_failed",
    "desktop_release_signing_key_not_loaded", "desktop_release_signing_key_untrusted", "desktop_release_signing_not_set_up", "desktop_release_signing_required_for_public_release",
    "desktop_release_update_conflict", "desktop_release_update_entry_untrusted",
    "desktop_release_source_unreadable", "desktop_release_source_unsettled", "desktop_release_sqlite_integrity_invalid",
    "desktop_release_symlink_rejected", "desktop_release_transitive_source_closure_invalid",
    "desktop_release_worker_unavailable",
    "desktop_release_write_failed", "synthetic_desktop_release_failpoint"
  )
}

# relative_path nur bei desktop_release_source_unreadable (#568): der unlesbare Eintrag, relativ zum Datenraum.
.desktop_release_condition_v1 <- function(code, relative_path = NULL) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% desktop_release_error_codes_v1()) {
    stop("unregistered_desktop_release_error_code", call. = FALSE)
  }
  shown <- if (identical(code, "desktop_release_source_unreadable")) .desktop_release_shown_path_v1(relative_path) else NULL
  structure(c(list(message = code, call = NULL, code = code), if (!is.null(shown)) list(relative_path = shown)),
            class = c("spot_desktop_release_error_v1", "error", "condition"))
}
.desktop_release_shown_path_v1 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) || nchar(value, type = "chars") > 1000L ||
      startsWith(value, "/") || grepl("(^|/)\\.\\.(/|$)", value) || grepl("[[:cntrl:]]", value)) return(NULL)
  value
}
.desktop_release_abort_v1 <- function(code, relative_path = NULL) stop(.desktop_release_condition_v1(code, relative_path))
.desktop_release_boundary_v1 <- function(expression) {
  result <- tryCatch(
    expression,
    spot_desktop_release_error_v1 = function(error) error,
    spot_desktop_product_error_v1 = function(error) .desktop_release_condition_v1("desktop_release_session_invalid"),
    error = function(error) .desktop_release_condition_v1("desktop_release_boundary_failed")
  )
  if (inherits(result, "spot_desktop_release_error_v1")) stop(result)
  result
}
.desktop_release_project_version_v1 <- function(project_root) {
  project <- .desktop_product_project_v1(project_root)
  tryCatch(
    .desktop_product_version_v1(project),
    spot_desktop_product_error_v1 = function(error) .desktop_release_abort_v1("desktop_release_release_integrity_invalid")
  )
}
# Programmstand eines Backups (#489, rc.429): der des INSTALLIERTEN Portelyra, das den Datenraum schreibt, nicht der des Ordners, aus dem
# der Befehl gerade laeuft. Aus einem Entwicklungsordner, der schon den naechsten Stand traegt, trug das Backup vor dem Update sonst dessen
# Nummer, und der Einrichtungsdialog des alten Stands wiese es als neueren Programmstand ab (Rollout rc.428). Ohne Installation
# (Entwicklung, Tests) der Stand des Ordners.
.desktop_release_backup_version_v1 <- function(project_root, home) {
  library <- .desktop_product_home_paths_v1(.desktop_product_normalize_existing_v1(home))$library
  installed <- file.path(library, ".portelyra-source")
  if (!dir.exists(installed) || .desktop_product_symlink_v1(installed)) return(.desktop_release_project_version_v1(project_root))
  tryCatch(
    .desktop_product_version_v1(installed),
    spot_desktop_product_error_v1 = function(error) .desktop_release_abort_v1("desktop_release_release_integrity_invalid")
  )
}
.desktop_release_path_v1 <- function(value) {
  if (!.desktop_product_absolute_v1(value) || grepl("[[:cntrl:]]", value)) .desktop_release_abort_v1("desktop_release_input_invalid")
  path.expand(value)
}
# Quelle eines Backups (rc.410): "strict" prueft Besitzer und Rechte (Backup-Ordner von Portelyra), "ignored" nur die Lesbarkeit - fuer
# einen vom Nutzer genannten Ordner, der nur gelesen wird (Wechselmedium ohne Rechteverwaltung, Datentraeger eines anderen Rechners).
# Das Feld geht nur mit, wenn es von der Vorgabe abweicht.
.desktop_release_source_permissions_v1 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !(value %in% c("strict", "ignored"))) .desktop_release_abort_v1("desktop_release_input_invalid")
  if (identical(value, "ignored")) list(source_permissions = "ignored") else list()
}
.desktop_release_sort_json_v1 <- function(value) {
  if (is.list(value) && !is.null(names(value))) {
    keys <- sort(names(value), method = "radix")
    return(stats::setNames(lapply(keys, function(key) .desktop_release_sort_json_v1(value[[key]])), keys))
  }
  if (is.list(value)) return(lapply(value, .desktop_release_sort_json_v1))
  value
}
.desktop_release_worker_v1 <- function(project_root, payload) {
  project <- .desktop_product_project_v1(project_root)
  script <- file.path(project, "scripts", "desktop_release.py")
  python <- Sys.which("python3")
  if (!nzchar(python) || !file.exists(script) || .desktop_product_symlink_v1(script)) {
    .desktop_release_abort_v1("desktop_release_worker_unavailable")
  }
  old_umask <- Sys.umask("0077")
  on.exit(Sys.umask(old_umask), add = TRUE)
  payload_json <- as.character(jsonlite::toJSON(
    .desktop_release_sort_json_v1(payload), auto_unbox = TRUE, null = "null", na = "null", digits = NA, pretty = FALSE
  ))
  envelope <- list(
    contract_version = 1L, payload_json = payload_json,
    payload_fingerprint = digest::digest(charToRaw(enc2utf8(payload_json)), algo = "sha256", serialize = FALSE)
  )
  job <- tempfile("portelyra-desktop-release-job-", fileext = ".json")
  on.exit(if (file.exists(job)) unlink(job, force = TRUE), add = TRUE)
  connection <- file(job, open = "wb")
  writeBin(charToRaw(enc2utf8(as.character(jsonlite::toJSON(
    envelope, auto_unbox = TRUE, null = "null", na = "null", digits = NA, pretty = FALSE
  )))), connection)
  close(connection)
  suppressWarnings(Sys.chmod(job, mode = "0600"))
  if (!.desktop_product_owner_mode_v1(job)) .desktop_release_abort_v1("desktop_release_permissions_invalid")
  output <- suppressWarnings(system2(
    python, c(shQuote(script), "--job", shQuote(job)), stdout = TRUE, stderr = TRUE,
    env = c("PYTHONDONTWRITEBYTECODE=1")
  ))
  status <- attr(output, "status"); if (is.null(status)) status <- 0L
  if (length(output) != 1L) .desktop_release_abort_v1("desktop_release_worker_unavailable")
  result <- tryCatch(jsonlite::fromJSON(output[[1L]], simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(result) || !is.character(result$status) || length(result$status) != 1L) {
    .desktop_release_abort_v1("desktop_release_worker_unavailable")
  }
  if (status != 0L || identical(result$status, "blocked")) {
    code <- result$code
    if (!is.character(code) || length(code) != 1L || !code %in% desktop_release_error_codes_v1()) code <- "desktop_release_boundary_failed"
    .desktop_release_abort_v1(code, result$relative_path)
  }
  result
}
.desktop_release_with_session_v1 <- function(home, expression) {
  home <- .desktop_product_normalize_existing_v1(home)
  lock <- file.path(home, "desktop-session.lock")
  owner <- .desktop_product_acquire_lock_v1(lock, "desktop_product_session_conflict")
  on.exit(if (dir.exists(lock)) .desktop_product_release_lock_v1(lock, owner), add = TRUE)
  force(expression(owner))
}

desktop_release_backup_v1 <- function(project_root, home = desktop_product_default_home_v1(), target_bundle, confirmation) {
  .desktop_release_boundary_v1({
    if (!identical(confirmation, "CREATE_OWNER_BACKUP")) .desktop_release_abort_v1("desktop_release_confirmation_required")
    target <- .desktop_release_path_v1(target_bundle)
    version <- .desktop_release_backup_version_v1(project_root, home)
    created <- format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    .desktop_release_with_session_v1(home, function(owner) .desktop_release_worker_v1(project_root, list(
      contract_version = 1L, operation = "backup", source_home = normalizePath(home, winslash = "/", mustWork = TRUE),
      session_nonce = owner$nonce, target_bundle = target, product_version = version, created_at_utc = created
    )))
  })
}

# Backup aus der laufenden Sitzung (#559, rc.407): „Backup anlegen“ in Data, ohne Portelyra zu beenden. Statt die Sitzungssperre
# zu uebernehmen (die haelt der Startprozess), bindet sich der Worker an deren Inhaber - nur wenn dieser Prozess wirklich laeuft.
# Gleichzeitige Schreibvorgaenge sichert der Worker selbst ab (dauerhafte Schreibsperren der Speicher, Abbruch bei unruhigem Stand:
# desktop_release_source_unsettled); Zeitlaeufe und „Alles aktualisieren“ haelt die Wartungssperre des Aufrufers an.
desktop_release_backup_in_session_v1 <- function(project_root, home = desktop_product_default_home_v1(), target_bundle, confirmation) {
  .desktop_release_boundary_v1({
    if (!identical(confirmation, "CREATE_OWNER_BACKUP")) .desktop_release_abort_v1("desktop_release_confirmation_required")
    target <- .desktop_release_path_v1(target_bundle)
    version <- .desktop_release_backup_version_v1(project_root, home)
    created <- format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    home <- .desktop_product_normalize_existing_v1(home)
    owner_path <- file.path(home, "desktop-session.lock", "owner.json")
    owner <- if (.desktop_product_symlink_v1(owner_path)) NULL else tryCatch(jsonlite::fromJSON(owner_path, simplifyVector = FALSE), error = function(error) NULL)
    if (!.desktop_product_lock_active_v1(owner)) .desktop_release_abort_v1("desktop_release_session_invalid")
    .desktop_release_worker_v1(project_root, list(
      contract_version = 1L, operation = "backup", source_home = normalizePath(home, winslash = "/", mustWork = TRUE),
      session_nonce = owner$nonce, target_bundle = target, product_version = version, created_at_utc = created
    ))
  })
}

# Die Backups eines Ordners, schnell und ohne Pruefsummen (#559, rc.407): Name, Zeitpunkt, Programmstand, Groesse, eigener
# Datenraum (mit `home`) und ob ein neuerer Programmstand sie schrieb. Ob ein Backup unversehrt ist, sagt erst backup_check.
desktop_release_backup_list_v1 <- function(project_root, root, home = NULL, source_permissions = "strict") {
  .desktop_release_boundary_v1(.desktop_release_worker_v1(project_root, c(list(
    contract_version = 1L, operation = "backup_list", root = .desktop_release_path_v1(root),
    product_version = .desktop_release_project_version_v1(project_root),
    home = if (is.null(home)) NULL else normalizePath(home, winslash = "/", mustWork = TRUE)
  ), .desktop_release_source_permissions_v1(source_permissions))))
}

# Wiederherstellen im Einrichtungsdialog (#559 Teil 2, rc.408): in das gerade eingerichtete Home der laufenden Sitzung (die Seite laeuft
# als Kind des Startprozesses, der die Sitzungssperre haelt). Ein Backup aus einem neueren Programmstand wird abgewiesen.
desktop_release_restore_fresh_v1 <- function(project_root, home, bundle, source_permissions = "strict") {
  .desktop_release_boundary_v1({
    source <- .desktop_release_source_permissions_v1(source_permissions)
    home <- .desktop_product_normalize_existing_v1(home)
    owner_path <- file.path(home, "desktop-session.lock", "owner.json")
    owner <- if (.desktop_product_symlink_v1(owner_path)) NULL else tryCatch(jsonlite::fromJSON(owner_path, simplifyVector = FALSE), error = function(error) NULL)
    if (!.desktop_product_lock_active_v1(owner)) .desktop_release_abort_v1("desktop_release_session_invalid")
    .desktop_release_worker_v1(project_root, c(list(
      contract_version = 1L, operation = "restore_fresh", source_home = normalizePath(home, winslash = "/", mustWork = TRUE),
      session_nonce = owner$nonce, bundle = .desktop_release_path_v1(bundle), product_version = .desktop_release_project_version_v1(project_root)
    ), source))
  })
}

desktop_release_backup_check_v1 <- function(project_root, bundle, source_permissions = "strict") {
  .desktop_release_boundary_v1(.desktop_release_worker_v1(project_root, c(list(
    contract_version = 1L, operation = "backup_check", bundle = .desktop_release_path_v1(bundle)
  ), .desktop_release_source_permissions_v1(source_permissions))))
}

# Alte Backups ausduennen (#438): behalten werden die keep juengsten gueltigen Backups desselben Datenraums. Ohne plan nur der
# Plan (Zaehler, Zeitpunkte, Groessen); mit plan und der Bestaetigung PRUNE_OWNER_BACKUPS genau dieser Plan, sonst nichts.
# `home` (rc.410): nur die Backups von dessen Datenraum - der Backup-Ordner gehoert allen Homes eines Benutzerkontos.
desktop_release_backup_prune_v1 <- function(project_root, root, keep, plan = NULL, confirmation = NULL, home = NULL) {
  .desktop_release_boundary_v1({
    if (!is.character(keep) || length(keep) != 1L || !grepl("^[1-9][0-9]?$", keep)) .desktop_release_abort_v1("desktop_release_input_invalid")
    if (is.null(plan) != is.null(confirmation)) .desktop_release_abort_v1("desktop_release_input_invalid")
    if (!is.null(plan) && !identical(confirmation, "PRUNE_OWNER_BACKUPS")) .desktop_release_abort_v1("desktop_release_confirmation_required")
    if (!is.null(plan) && (!is.character(plan) || length(plan) != 1L || !grepl("^[a-f0-9]{64}$", plan))) .desktop_release_abort_v1("desktop_release_input_invalid")
    .desktop_release_worker_v1(project_root, list(
      contract_version = 1L, operation = "backup_prune", root = .desktop_release_path_v1(root), keep = as.integer(keep),
      plan_fingerprint = if (is.null(plan)) NULL else plan,
      home = if (is.null(home)) NULL else normalizePath(home, winslash = "/", mustWork = TRUE)
    ))
  })
}

desktop_release_restore_preflight_v1 <- function(project_root, bundle, target_home) {
  .desktop_release_boundary_v1(.desktop_release_worker_v1(project_root, list(
    contract_version = 1L, operation = "restore_preflight", bundle = .desktop_release_path_v1(bundle),
    target_home = .desktop_release_path_v1(target_home)
  )))
}

desktop_release_restore_v1 <- function(
  project_root, home = desktop_product_default_home_v1(), bundle, target_home, confirmation
) {
  .desktop_release_boundary_v1({
    if (!identical(confirmation, "RESTORE_TO_EMPTY_DESKTOP")) .desktop_release_abort_v1("desktop_release_confirmation_required")
    bundle <- .desktop_release_path_v1(bundle); target <- .desktop_release_path_v1(target_home)
    .desktop_release_with_session_v1(home, function(owner) .desktop_release_worker_v1(project_root, list(
      contract_version = 1L, operation = "restore", source_home = normalizePath(home, winslash = "/", mustWork = TRUE),
      session_nonce = owner$nonce, bundle = bundle, target_home = target
    )))
  })
}

desktop_release_build_v1 <- function(project_root, archive, confirmation) {
  .desktop_release_boundary_v1({
    if (!identical(confirmation, "BUILD_LOCAL_RELEASE")) .desktop_release_abort_v1("desktop_release_confirmation_required")
    .desktop_release_worker_v1(project_root, list(
      contract_version = 1L, operation = "release_build", project_root = .desktop_product_project_v1(project_root),
      archive = .desktop_release_path_v1(archive), product_version = .desktop_release_project_version_v1(project_root)
    ))
  })
}

desktop_release_check_v1 <- function(project_root, archive) {
  .desktop_release_boundary_v1(.desktop_release_worker_v1(project_root, list(
    contract_version = 1L, operation = "release_check", archive = .desktop_release_path_v1(archive),
    project_root = .desktop_product_project_v1(project_root)
  )))
}

# Update aus einem Archiv (#486 Schritt 3, Festlegung 16.11.2026): Nur das INSTALLIERTE Portelyra darf es einspielen - wer
# den Befehl aus dem entpackten Archiv startet, fuehrt dessen Code schon aus, eine Pruefung darin schuetzte nichts. Geprueft wird gegen die
# Vertrauensliste des installierten Release: leer -> wie bisher ohne Signatur; mit Schluessel -> nur signiert, ohne Ausnahme. Danach wie
# `upgrade` aus dem entpackten Ordner; der Ordner wird am Ende entfernt.
desktop_product_update_v1 <- function(project_root, home = desktop_product_default_home_v1(), archive, confirmation) {
  if (!identical(confirmation, "UPGRADE_LOCAL_RUNTIME")) .desktop_product_abort_v1("desktop_product_upgrade_confirmation_required")
  staged <- desktop_product_update_stage_v1(project_root, home, archive)
  on.exit(desktop_product_update_unstage_v1(staged), add = TRUE)
  result <- .desktop_product_upgrade_impl_v1(staged$candidate, staged$home, confirmation, fail_at = "none", candidate_scope = "own")
  c(result, list(signature = staged$signature))
}

# Erster Schritt des Updates (#489, rc.429): das Archiv pruefen und nach <home>/update-staging entpacken - noch nichts eingespielt. Nur
# das installierte Portelyra darf das (siehe oben). Zurueck: geprueft und entpackt (`candidate`), Signatur, Version des Archivs und des
# installierten Stands, und ob das Archiv genau dem installierten Stand entspricht (`already_current`) oder neuer ist (`newer`). Den
# Ordner raeumt desktop_product_update_unstage_v1 ab, auch nach einem Fehler.
desktop_product_update_stage_v1 <- function(project_root, home, archive) {
  home <- .desktop_product_normalize_existing_v1(home)
  root <- .desktop_product_project_v1(project_root)
  active <- tryCatch(.desktop_product_active_source_v1(home), error = function(error) NULL)
  if (is.null(active) || !identical(root, active)) .desktop_release_abort_v1("desktop_release_update_entry_untrusted")
  staging <- file.path(home, "update-staging")
  # Wie bisher: Nach einem Abbruch bleibt kein Entpack-Ordner liegen, auch kein alter - er blockierte sonst jedes naechste Update.
  tryCatch({
    staged <- .desktop_release_boundary_v1(.desktop_release_worker_v1(root, list(
      contract_version = 1L, operation = "release_update_stage", archive = .desktop_release_path_v1(archive), staging = staging,
      trust_list = file.path(root, "contracts", "plugin-signing", "v1", "allowed_signers")
    )))
    candidate <- file.path(staging, paste0("portelyra-", staged$product_version))
    # #571 (rc.433): Manifest und Signatur hat der Worker geprueft; im entpackten Stand gehoeren sie nicht zum Programm. Ohne sie traegt der
    # Stand genau die Dateien seines Registers, und nur gegen dieses wird er geprueft (nicht gegen die eingebaute Liste dieses Codes).
    for (name in c("release-manifest.json", "release-manifest.json.sig")) {
      meta <- file.path(candidate, name)
      if (file.exists(meta) && !dir.exists(meta) && !.desktop_product_symlink_v1(meta)) unlink(meta, force = TRUE)
    }
    current <- .desktop_product_library_manifest_v1(.desktop_product_home_paths_v1(home)$library)
    list(home = home, staging = staging, candidate = candidate, signature = staged$signature, product_version = staged$product_version,
         installed_version = current$product_version,
         already_current = identical(.desktop_product_source_fingerprint_v1(candidate, enforce_current_scope = FALSE), current$source_fingerprint),
         newer = .desktop_product_version_newer_v1(staged$product_version, current$product_version))
  }, error = function(error) {
    desktop_product_update_unstage_v1(list(staging = staging))
    stop(error)
  })
}
desktop_product_update_unstage_v1 <- function(staged) {
  staging <- staged$staging
  if (is.character(staging) && length(staging) == 1L && dir.exists(staging) && !.desktop_product_symlink_v1(staging)) {
    unlink(staging, recursive = TRUE, force = TRUE)
  }
  invisible(NULL)
}

desktop_release_private_acceptance_v1 <- function(
  project_root, home = desktop_product_default_home_v1(), bundle, restored_home
) {
  tryCatch(
    .desktop_release_with_session_v1(home, function(owner) {
      result <- .desktop_release_worker_v1(project_root, list(
        contract_version = 1L, operation = "acceptance_check",
        source_home = normalizePath(home, winslash = "/", mustWork = TRUE), session_nonce = owner$nonce,
        bundle = .desktop_release_path_v1(bundle), restored_home = .desktop_release_path_v1(restored_home)
      ))
      if (identical(result$status, "pass")) list(status = "pass") else list(status = "fail", code = "desktop_release_acceptance_failed")
    }),
    error = function(error) {
      code <- tryCatch(error$code, error = function(condition) NULL)
      if (!is.character(code) || length(code) != 1L || !startsWith(code, "desktop_release_")) code <- "desktop_release_acceptance_failed"
      list(status = "fail", code = code)
    }
  )
}
