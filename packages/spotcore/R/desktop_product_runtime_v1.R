desktop_product_error_codes_v1 <- function() {
  c(
    "desktop_product_platform_unsupported",
    "desktop_product_dependency_missing",
    "desktop_product_cli_input_invalid",
    "desktop_product_project_invalid",
    "desktop_product_home_invalid",
    "desktop_product_home_inside_project",
    "desktop_product_symlink_rejected",
    "desktop_product_permissions_invalid",
    "desktop_product_install_confirmation_required",
    "desktop_product_install_failed",
    "desktop_product_install_conflict",
    "desktop_product_session_conflict",
    "desktop_product_upgrade_confirmation_required",
    "desktop_product_upgrade_unavailable",
    "desktop_product_upgrade_recovery_required",
    "desktop_product_update_busy",
    "desktop_product_update_stop_failed",
    "desktop_product_update_preflight_failed",
    "desktop_product_rollback_confirmation_required",
    "desktop_product_rollback_incompatible",
    "desktop_product_rollback_unavailable",
    "desktop_product_release_version_invalid",
    "desktop_product_registry_confirmation_required",
    "desktop_product_registry_invalid",
    "desktop_product_registry_conflict",
    "desktop_product_not_initialized",
    "desktop_product_context_invalid",
    "desktop_product_data_space_confirmation_required",
    "desktop_product_workspace_invalid",
    "desktop_product_locked",
    "desktop_product_protection_invalid",
    "desktop_product_boundary_failed"
  )
}

.desktop_product_condition_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% desktop_product_error_codes_v1()) {
    stop("unregistered_desktop_product_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_desktop_product_error_v1", "error", "condition")
  )
}

.desktop_product_abort_v1 <- function(code) stop(.desktop_product_condition_v1(code))

.desktop_product_boundary_v1 <- function(expression, fallback = "desktop_product_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_desktop_product_error_v1 = function(error) error,
    # Fachliche Fehler der Adapter tragen einen geprueften Code aus einer
    # geschlossenen Liste; sie gehen unveraendert durch. Ohne das wuerde jeder
    # davon zum Sammelcode desktop_product_boundary_failed, und die Ursache
    # bliebe verborgen: Ein abgelehnter Verkauf meldete sonst nur
    # "Aktion blockiert", obwohl der Kern genau weiss, dass die Gebuehr nicht
    # null sein darf (#422).
    spot_desktop_product_adapter_domain_error = function(error) stop(error),
    spot_runtime_error = function(error) .desktop_product_condition_v1("desktop_product_context_invalid"),
    spot_canonical_repository_error = function(error) .desktop_product_condition_v1("desktop_product_workspace_invalid"),
    spot_catalog_data_command_error = function(error) .desktop_product_condition_v1("desktop_product_workspace_invalid"),
    spot_transaction_data_command_error = function(error) .desktop_product_condition_v1("desktop_product_workspace_invalid"),
    error = function(error) .desktop_product_condition_v1(fallback)
  )
  if (inherits(result, "spot_desktop_product_error_v1")) stop(result)
  result
}

.desktop_product_utc_valid_v1 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)) return(FALSE)
  parsed <- suppressWarnings(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  !is.na(parsed) && identical(format(parsed, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), value)
}

.desktop_product_label_valid_v1 <- function(value, maximum = 100L) {
  is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value) &&
    identical(value, trimws(value)) && nchar(value, type = "bytes") <= maximum &&
    !grepl("[[:cntrl:]@/\\\\]", value)
}

.desktop_product_symlink_v1 <- function(path) {
  link <- suppressWarnings(Sys.readlink(path))
  length(link) == 1L && !is.na(link) && nzchar(link)
}

.desktop_product_absolute_v1 <- function(path) {
  is.character(path) && length(path) == 1L && !is.na(path) && nzchar(path) && startsWith(path.expand(path), "/")
}

.desktop_product_existing_ancestor_v1 <- function(path) {
  current <- path.expand(path)
  repeat {
    if (file.exists(current) || dir.exists(current)) return(current)
    parent <- dirname(current)
    if (identical(parent, current)) .desktop_product_abort_v1("desktop_product_home_invalid")
    current <- parent
  }
}

.desktop_product_assert_no_symlink_v1 <- function(path) {
  current <- path.expand(path)
  ancestor <- .desktop_product_existing_ancestor_v1(current)
  existing <- character()
  repeat {
    existing <- c(ancestor, existing)
    parent <- dirname(ancestor)
    if (identical(parent, ancestor)) break
    ancestor <- parent
  }
  for (item in existing) if (.desktop_product_symlink_v1(item)) .desktop_product_abort_v1("desktop_product_symlink_rejected")
  if ((file.exists(current) || dir.exists(current)) && .desktop_product_symlink_v1(current)) {
    .desktop_product_abort_v1("desktop_product_symlink_rejected")
  }
  invisible(TRUE)
}

.desktop_product_normalize_existing_v1 <- function(path, code = "desktop_product_home_invalid") {
  if (!.desktop_product_absolute_v1(path)) .desktop_product_abort_v1(code)
  .desktop_product_assert_no_symlink_v1(path)
  normalized <- tryCatch(normalizePath(path.expand(path), winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(normalized)) .desktop_product_abort_v1(code)
  normalized
}

.desktop_product_owner_mode_v1 <- function(path, directory = FALSE) {
  if (!(if (directory) dir.exists(path) else file.exists(path) && !dir.exists(path))) return(FALSE)
  mode <- suppressWarnings(as.integer(file.info(path)$mode))
  length(mode) == 1L && !is.na(mode) && bitwAnd(mode, 63L) == 0L
}

.desktop_product_enforce_dir_v1 <- function(path) {
  old_umask <- Sys.umask("0077")
  on.exit(Sys.umask(old_umask), add = TRUE)
  if (file.exists(path) && !dir.exists(path)) .desktop_product_abort_v1("desktop_product_home_invalid")
  if (!dir.exists(path) && !dir.create(path, recursive = FALSE, mode = "0700", showWarnings = FALSE)) {
    .desktop_product_abort_v1("desktop_product_home_invalid")
  }
  if (.desktop_product_symlink_v1(path)) .desktop_product_abort_v1("desktop_product_symlink_rejected")
  suppressWarnings(Sys.chmod(path, mode = "0700"))
  if (!.desktop_product_owner_mode_v1(path, directory = TRUE)) .desktop_product_abort_v1("desktop_product_permissions_invalid")
  invisible(path)
}

.desktop_product_ensure_home_v1 <- function(home) {
  old_umask <- Sys.umask("0077")
  on.exit(Sys.umask(old_umask), add = TRUE)
  if (!.desktop_product_absolute_v1(home)) .desktop_product_abort_v1("desktop_product_home_invalid")
  expanded <- path.expand(home)
  .desktop_product_assert_no_symlink_v1(expanded)
  # Wie preflight der naechste vorhandene Ordner (#489, rc.431): Ein frisch angelegtes Benutzerkonto hat noch kein ~/.local/share - die
  # Installation brach dort mit desktop_product_home_invalid ab, obwohl preflight ready_to_install meldete (Probe im Container 17.11.2026).
  parent <- .desktop_product_normalize_existing_v1(.desktop_product_existing_ancestor_v1(dirname(expanded)))
  if (!dir.exists(parent) || file.access(parent, 2L) != 0L) .desktop_product_abort_v1("desktop_product_home_invalid")
  if (!dir.exists(expanded)) {
    if (!dir.create(expanded, recursive = TRUE, mode = "0700", showWarnings = FALSE)) {
      .desktop_product_abort_v1("desktop_product_home_invalid")
    }
  }
  .desktop_product_assert_no_symlink_v1(expanded)
  suppressWarnings(Sys.chmod(expanded, mode = "0700"))
  normalized <- .desktop_product_normalize_existing_v1(expanded)
  if (!dir.exists(normalized) || !.desktop_product_owner_mode_v1(normalized, directory = TRUE)) {
    .desktop_product_abort_v1("desktop_product_permissions_invalid")
  }
  normalized
}

# Passwortschutz (#535, rc.396): Mit `protection.json` im Home liegt der Datenbestand in einem verschluesselten Ordner, entsperrt
# eingehaengt unter $XDG_RUNTIME_DIR/portelyra-<sha256(Home)[1:12]>/data - dieselbe Rechnung wie desktop_protection_v1.mount_root_v1.
# Ohne die Datei bleibt alles wie bisher (<home>/data).
.desktop_product_protection_v1 <- function(home) {
  state <- file.path(home, "protection.json")
  if (!file.exists(state)) return(NULL)
  value <- tryCatch(jsonlite::fromJSON(state, simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(value) || !identical(value$contract_version, "desktop_protection_v1") || !isTRUE(value$enabled))
    .desktop_product_abort_v1("desktop_product_protection_invalid")
  runtime <- Sys.getenv("XDG_RUNTIME_DIR", unset = "")
  if (!nzchar(runtime)) runtime <- file.path("/run/user", tryCatch(system2("id", "-u", stdout = TRUE), error = function(error) ""))
  resolved <- normalizePath(home, winslash = "/", mustWork = TRUE)
  root <- file.path(runtime, paste0("portelyra-", substr(digest::digest(resolved, algo = "sha256", serialize = FALSE), 1L, 12L)))
  data <- file.path(root, "data")
  mounted <- function(path) dir.exists(path) && identical(suppressWarnings(system2("mountpoint", c("-q", shQuote(path)))), 0L)
  list(root = root, data = data, backups = file.path(root, "backups"), unlocked = mounted(data))
}

.desktop_product_home_paths_v1 <- function(home) {
  protection <- .desktop_product_protection_v1(home)
  list(
    home = home,
    registry = file.path(home, "desktop-runtime.json"),
    data_root = if (is.null(protection)) file.path(home, "data") else protection$data,
    protected = !is.null(protection),
    locked = !is.null(protection) && !isTRUE(protection$unlocked),
    library = file.path(home, "library"),
    install_manifest = file.path(home, "library", ".portelyra-install.json"),
    rollback_library = file.path(home, "rollback-library"),
    upgrade_staging = file.path(home, ".desktop-library-upgrade-staging"),
    rollback_staging = file.path(home, ".desktop-library-rollback-staging"),
    upgrade_journal = file.path(home, ".desktop-upgrade-journal.json"),
    upgrade_receipts = file.path(home, "upgrade-receipts")
  )
}

# Eigene Einheit fuer die App (#588, 0.3.3). Tresor und Waechter laufen seit #587 in eigenen Einheiten der Sitzung, die App bisher nicht:
# Startete `update` sie (Schritt 6 oder Neustart nach einem Abbruch), lag sie in der Gruppe des Aufrufers, etwa des Terminals. Beendet
# systemd-oomd diese Gruppe bei Speicherdruck, endete Portelyra mit, ohne geordnet herunterzufahren. Der Vorsatz `prefix` legt den
# abgekoppelten Start in eine eigene Einheit (systemd-run --user --scope, benannt wie der Tresor: portelyra-app-<sha256(Home)[1:12]>-<Zufall>);
# die Umgebung bleibt, Browser und Schluesselbund gehen weiter. Eine kurze Probe stellt vorher sicher, dass der Benutzerdienst Einheiten
# annimmt. Ohne systemd-run, ohne Benutzerdienst (Container, Server) oder wenn die Probe scheitert, bleibt `prefix` leer, und `reason` nennt
# den Grund. Der Start ueber das Dock hat schon eine eigene Gruppe; ein Start aus der Shell bleibt im Vordergrund der Shell, wo Strg+C ihn
# beendet. PORTELYRA_APP_UNIT_INTERNAL=off schaltet die Einheit ab (Fehlersuche). `kind` "update" (#562 Paket 4): das Einspielen aus der
# App laeuft so in portelyra-update-<…> und ueberlebt das Beenden der App, die es angestossen hat.
.desktop_product_app_unit_v1 <- function(home, tool = unname(Sys.which("systemd-run")), runtime = Sys.getenv("XDG_RUNTIME_DIR", unset = ""),
                                         switch = Sys.getenv("PORTELYRA_APP_UNIT_INTERNAL", unset = ""),
                                         probe = function(command) suppressWarnings(system2(command[[1L]], c(command[-1L], "true"), stdout = FALSE, stderr = FALSE)),
                                         kind = "app") {
  if (!identical(kind, "app") && !identical(kind, "update")) stop("desktop_product_app_unit_kind_invalid", call. = FALSE)
  none <- function(reason) list(prefix = character(), unit = NULL, reason = reason)
  if (identical(switch, "off")) return(none("disabled"))
  if (!nzchar(tool)) return(none("systemd_run_missing"))
  if (!nzchar(runtime) || !file.exists(file.path(runtime, "systemd", "private"))) return(none("user_manager_missing"))
  probed <- tryCatch(as.integer(probe(c(tool, "--user", "--scope", "--quiet", "--collect"))), error = function(error) NA_integer_)
  if (!identical(probed, 0L)) return(none("systemd_run_failed"))
  resolved <- normalizePath(home, winslash = "/", mustWork = TRUE)
  id <- substr(digest::digest(resolved, algo = "sha256", serialize = FALSE), 1L, 12L)
  nonce <- substr(digest::digest(paste(Sys.getpid(), format(Sys.time(), "%Y-%m-%d %H:%M:%OS6"), stats::runif(1L)),
                                 algo = "sha256", serialize = FALSE), 1L, 8L)
  unit <- paste0("portelyra-", kind, "-", id, "-", nonce)
  list(prefix = c(tool, "--user", "--scope", "--quiet", "--collect", paste0("--unit=", unit)), unit = unit, reason = NULL)
}

# Bildmarke (#584, 0.3.3): `apps/shared/icons` des Programms als Symbol "portelyra" ins Symbolthema der Sitzung
# ($XDG_DATA_HOME/icons/hicolor: scalable als SVG, dazu die PNG-Groessen) - fuer Starter und Hinweise am Bildschirmrand. Kopiert wird
# nur, was fehlt oder sich unterscheidet, je Datei ueber eine temporaere Datei und Umbenennen; Ziele, die symbolische Links sind, bleiben
# unberuehrt. Ergebnis TRUE, wenn das SVG danach dort liegt; ohne Bildmarke im Programm FALSE (dann bleibt das allgemeine Symbol).
.desktop_product_icon_sizes_v1 <- c(16L, 24L, 32L, 48L, 64L, 128L, 256L)
.desktop_product_data_home_v1 <- function() {
  data_home <- Sys.getenv("XDG_DATA_HOME", unset = "")
  if (nzchar(data_home)) data_home else file.path(path.expand("~"), ".local", "share")
}
.desktop_product_icon_install_v1 <- function(source_root, data_home = .desktop_product_data_home_v1()) {
  icons <- file.path(source_root, "apps", "shared", "icons")
  files <- c(stats::setNames(file.path(icons, "portelyra.svg"), file.path("scalable", "apps", "portelyra.svg")),
             stats::setNames(file.path(icons, sprintf("portelyra-%d.png", .desktop_product_icon_sizes_v1)),
                             file.path(sprintf("%1$dx%1$d", .desktop_product_icon_sizes_v1), "apps", "portelyra.png")))
  if (!file.exists(files[[1L]])) return(FALSE)
  hicolor <- file.path(data_home, "icons", "hicolor")
  for (relative in names(files)) {
    source <- files[[relative]]
    target <- file.path(hicolor, relative)
    if (!file.exists(source) || .desktop_product_symlink_v1(target)) next
    if (file.exists(target) && identical(digest::digest(file = target, algo = "sha256"), digest::digest(file = source, algo = "sha256"))) next
    if (!dir.exists(dirname(target))) dir.create(dirname(target), recursive = TRUE, mode = "0755")
    temporary <- paste0(target, ".tmp-", Sys.getpid())
    if (!file.copy(source, temporary, overwrite = TRUE)) next
    Sys.chmod(temporary, mode = "0644")
    if (!file.rename(temporary, target)) unlink(temporary)
  }
  svg <- file.path(hicolor, names(files)[[1L]])
  file.exists(svg) && !.desktop_product_symlink_v1(svg)
}

# Exec nach der Desktop-Entry-Spezifikation: jedes Argument in "…", darin " ` $ \ maskiert, % verdoppelt.
.desktop_product_entry_quote_v1 <- function(value) paste0('"', gsub("%", "%%", gsub('(["`$\\\\])', "\\\\\\1", value), fixed = TRUE), '"')

# Starter von vor 0.3.3 tragen das allgemeine Symbol. Sie bekommen die Bildmarke beim ersten Start des neuen Stands, denn ein Update fuehrt
# noch den Code des alten Stands aus und kennt sie nicht (#584). Angefasst wird nur portelyra.desktop, und nur, wenn sein Start dieses
# Programm aufruft - ein Demo- oder Test-Home laesst den Starter des Eigentuemers stehen -, und darin nur die Zeile Icon=. Ergebnis:
# "updated", "current", "other_home", "no_entry", "icon_missing" oder "failed".
.desktop_product_entry_icon_refresh_v1 <- function(source_root, data_home = .desktop_product_data_home_v1()) {
  entry <- file.path(data_home, "applications", "portelyra.desktop")
  if (!file.exists(entry) || .desktop_product_symlink_v1(entry)) return("no_entry")
  lines <- tryCatch(readLines(entry, warn = FALSE, encoding = "UTF-8"), error = function(error) character())
  exec <- grep("^Exec=", lines, value = TRUE)
  script <- .desktop_product_entry_quote_v1(file.path(source_root, "scripts", "portelyra_desktop.R"))
  if (!length(exec) || !grepl(paste0(script, " start"), exec[[1L]], fixed = TRUE)) return("other_home")
  if (!isTRUE(.desktop_product_icon_install_v1(source_root, data_home))) return("icon_missing")
  icon <- grep("^Icon=", lines)
  if (length(icon) && all(lines[icon] == "Icon=portelyra")) return("current")
  lines <- if (length(icon)) replace(lines, icon, "Icon=portelyra") else append(lines, "Icon=portelyra", after = grep("^Exec=", lines)[[1L]])
  temporary <- paste0(entry, ".tmp-", Sys.getpid())
  written <- tryCatch({ writeLines(enc2utf8(lines), temporary, useBytes = TRUE); TRUE }, error = function(error) FALSE)
  if (!written) { unlink(temporary); return("failed") }
  Sys.chmod(temporary, mode = "0644")
  if (!file.rename(temporary, entry)) { unlink(temporary); return("failed") }
  "updated"
}

desktop_product_default_home_v1 <- function() {
  configured <- Sys.getenv("PORTELYRA_DESKTOP_HOME", unset = "")
  if (nzchar(configured)) return(path.expand(configured))
  xdg <- Sys.getenv("XDG_DATA_HOME", unset = "")
  if (nzchar(xdg)) return(file.path(path.expand(xdg), "portelyra"))
  home <- Sys.getenv("HOME", unset = "")
  if (!nzchar(home)) .desktop_product_abort_v1("desktop_product_home_invalid")
  file.path(path.expand(home), ".local", "share", "portelyra")
}

.desktop_product_project_v1 <- function(project_root) {
  root <- .desktop_product_normalize_existing_v1(project_root, "desktop_product_project_invalid")
  required <- c(
    "AGENTS.md", "VERSION", "packages/spotcore/DESCRIPTION", "packages/spotdisplay/DESCRIPTION",
    "apps/data/desktop_product_app_v1.R", "apps/shared/portelyra_ui_shell.R",
    "contracts/v2/schema.sql", "contracts/v2.1/migrate-from-v2.sql",
    "contracts/desktop-product/v1/source-fingerprints.csv"
  )
  if (!all(file.exists(file.path(root, required)))) .desktop_product_abort_v1("desktop_product_project_invalid")
  root
}

.desktop_product_is_within_v1 <- function(path, root) {
  identical(path, root) || startsWith(paste0(path, "/"), paste0(root, "/"))
}

.desktop_product_verify_source_registry_v1 <- function(project_root, enforce_current_scope = TRUE) {
  if (!is.logical(enforce_current_scope) || length(enforce_current_scope) != 1L || is.na(enforce_current_scope)) {
    .desktop_product_abort_v1("desktop_product_project_invalid")
  }
  registry_path <- file.path(project_root, "contracts", "desktop-product", "v1", "source-fingerprints.csv")
  rows <- tryCatch(read.csv(registry_path, stringsAsFactors = FALSE), error = function(error) NULL)
  if (is.null(rows) || !identical(names(rows), c("path", "sha256")) || nrow(rows) < 1L ||
      anyDuplicated(rows$path) || any(!grepl("^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$", rows$path)) ||
      any(vapply(strsplit(rows$path, "/", fixed = TRUE), function(parts) any(parts %in% c(".", "..")), logical(1))) ||
      any(!grepl("^[a-f0-9]{64}$", rows$sha256))) {
    .desktop_product_abort_v1("desktop_product_project_invalid")
  }
  fixed <- c(
    "apps/data/desktop_product_app_v1.R", "apps/data/data_asset_center_v1.R", "apps/data/data_portfolio_csv_exchange_v1.R", "apps/data/data_cash_statement_import_v1.R", "apps/data/data_securities_statement_import_v1.R", "apps/data/data_provider_mapping_editor_v1.R", "apps/data/data_provider_search_service_v1.R", "apps/data/data_provider_probe_service_v1.R", "apps/data/data_provider_promotion_service_v1.R", "apps/data/data_market_history_plan_service_v1.R", "apps/data/data_market_history_coverage_service_v1.R", "apps/data/data_market_history_carry_service_v1.R", "apps/data/data_market_history_fetch_service_v1.R", "apps/data/data_transaction_editor_v1.R", "apps/data/data_asset_activity_editor_v1.R", "apps/data/data_activity_draft_v1.R", "apps/data/data_activity_quick_import_v1.R", "apps/data/data_asset_activity_correction_v1.R", "apps/data/data_activity_block_reason_v1.R", "apps/data/data_net_amount_gross_v1.R", "apps/data/data_asset_center_filter_v1.R", "apps/data/data_asset_quantity_scale_revision_v1.R", "apps/data/data_asset_activity_csv_v1.R", "apps/data/data_cash_coverage_editor_v1.R", "apps/data/desktop_catalog_editor_v1.R",
    "apps/cockpit/desktop_product_app_v1.R", "apps/tax/desktop_product_app_v1.R", "apps/tax/tax_ui_service_v1.R", "apps/tax/tax_ui_view_model_v1.R",
    "apps/analysis/desktop_product_app_v1.R", "apps/shared/portelyra_ui_shell.R", "apps/shared/asset_selection_context_v1.R", "apps/shared/asset_selection_context_v2.R", "apps/shared/asset_selection_context_v3.R", "apps/shared/asset_filter_v1.R",
    "apps/shared/desktop_workflow_service_v1.R", "apps/shared/desktop_workflow_ui_v1.R",
    "apps/data/data_per_asset_legacy_review_v1.R", "apps/data/data_per_asset_legacy_review_ui_v1.R",
    "apps/data/data_per_asset_legacy_review_adapter_v1.R", "apps/data/data_per_asset_legacy_review_demo_adapter_v1.R",
    "apps/reference/latest_run_reader_v1.py", "apps/desktop_demo/read_latest_artifact_v1.py",
    "Portelyra.Rproj", "start_portelyra.R", "scripts/portelyra_desktop.R", "scripts/portfolio_csv_exchange.py", "scripts/portfolio_csv_handoff.py", "scripts/cash_coverage_store_migration.py", "scripts/desktop_workflow.py", "scripts/desktop_release_source_closure.py", "scripts/tax_ui_workspace.py", "scripts/desktop_provider_search.py", "scripts/desktop_provider_probe.py", "scripts/desktop_provider_probe_promotion.py", "scripts/desktop_market_history_plan.py", "scripts/desktop_market_history_coverage.py", "scripts/desktop_market_history_carry.py", "scripts/desktop_market_history_fetch.py", "scripts/realized_fifo_projection.R", "scripts/per_asset_legacy_review.py",
    "workers/reference/desktop_release_source_closure_v1.py", "workers/reference/desktop_workflow_v1.py", "workers/reference/run_publication_v1.py",
    "workers/reference/semantic_realized_fifo_v1.py", "workers/reference/semantic_realized_fifo_projector_v1.py",
    "workers/reference/trade_analysis_artifact_v1.py", "workers/reference/market_analysis_artifact_v1.py",
    "migrations/reference/desktop_product_asset_activity_v1.py", "migrations/reference/portfolio_csv_exchange_v1.py", "migrations/reference/portfolio_csv_handoffs_v1.py", "workers/import_plugin_sandbox_v1.py", "migrations/reference/cash_coverage_store_migration_v2900_to_v2901.py", "migrations/reference/desktop_provider_search_v1.py", "migrations/reference/desktop_provider_probe_v1.py", "migrations/reference/desktop_provider_probe_promotion_v1.py", "migrations/reference/desktop_market_history_plan_v1.py", "migrations/reference/desktop_market_history_coverage_v1.py", "migrations/reference/desktop_market_history_carry_v1.py", "migrations/reference/desktop_market_history_fetch_v1.py", "migrations/reference/desktop_product_asset_activity_view_v2.py", "migrations/reference/desktop_product_asset_activity_view_v3.py", "migrations/reference/desktop_product_asset_activity_view_v4.py", "migrations/reference/desktop_product_asset_activity_view_v5.py", "migrations/reference/desktop_asset_activity_correction_v1.py", "migrations/reference/desktop_asset_quantity_scale_revision_v1.py", "migrations/reference/desktop_activity_draft_v1.py", "migrations/reference/asset_activity_csv_import_v1.py", "migrations/reference/statement_reward_booked_match_v1.py", "migrations/reference/cash_statement_import_v1.py", "migrations/reference/redundant_asset_activity_csv_v1.py", "migrations/reference/standardized_legacy_activity_recovery_v1.py", "migrations/reference/desktop_cash_coverage_v1.py", "migrations/reference/schema400_asset_activity_compat_v1.py", "migrations/reference/tax_ui_workspace_v1.py",
    "workers/reference/asset_activity_realized_state_v2.py", "workers/reference/portfolio_operational_readiness_v1.py", "workers/reference/portfolio_snapshot_freshness_v1.py", "workers/reference/portfolio_snapshot_projection_v1.py", "workers/reference/portfolio_snapshot_publication_v1.py", "workers/reference/semantic_realized_fifo_v2.py",
    "contracts/desktop-product-asset-activity/v1/native-preview.schema.json", "contracts/desktop-product-asset-activity/v1/native-attempt.schema.json",
    "contracts/realized-materialization/v2/schema.sql", "contracts/asset-activity-csv/v1/portelyra-asset-activity.csv",
    "contracts/cash-coverage/v1/README.md", "contracts/cash-coverage/v1/cash-coverage-contract.md", "contracts/cash-coverage/v1/fresh-cash-operations.md",
    "contracts/cash-coverage/v1/schema-2900.sql", "contracts/cash-coverage/v1/schema.sql", "contracts/cash-coverage/v1/input.schema.json", "contracts/cash-coverage/v1/preview.schema.json", "contracts/cash-coverage/v1/command.schema.json",
    "contracts/cash-coverage/v1/command-preview.schema.json", "contracts/cash-coverage/v1/read-model.schema.json",
    "contracts/cash-coverage/v1/store-migration-public-preview.schema.json", "contracts/cash-coverage/v1/store-migration-trusted-preview.schema.json", "contracts/cash-coverage/v1/store-migration-confirmation.schema.json", "contracts/cash-coverage/v1/store-migration-attempt.schema.json", "contracts/cash-coverage/v1/store-migration-receipt.schema.json",
    "contracts/cash-coverage/v1/store-migration-recovery-public-preview.schema.json", "contracts/cash-coverage/v1/store-migration-recovery-trusted-preview.schema.json", "contracts/cash-coverage/v1/store-migration-recovery-confirmation.schema.json", "contracts/cash-coverage/v1/store-migration-recovery-attempt.schema.json",
    "contracts/cash-coverage/v1/capability-matrix.csv", "contracts/cash-coverage/v1/failure-codes.csv",
    "contracts/cash-coverage/v1/state-machine.csv", "contracts/cash-coverage/v1/source-fingerprints.csv",
    "contracts/asset-center/v1/README.md", "contracts/asset-center/v1/asset-center-contract.md", "contracts/asset-center/v1/capability-matrix.csv", "contracts/asset-center/v1/failure-codes.csv", "contracts/asset-center/v1/state-machine.csv", "contracts/asset-center/v1/source-fingerprints.csv",
    "contracts/asset-selection-context/v1/README.md", "contracts/asset-selection-context/v1/asset-selection-context-contract.md", "contracts/asset-selection-context/v1/capability-matrix.csv", "contracts/asset-selection-context/v1/failure-codes.csv", "contracts/asset-selection-context/v1/state-machine.csv", "contracts/asset-selection-context/v1/source-fingerprints.csv",
    "contracts/asset-selection-context/v2/README.md", "contracts/asset-selection-context/v2/asset-selection-context-contract.md", "contracts/asset-selection-context/v2/capability-matrix.csv", "contracts/asset-selection-context/v2/failure-codes.csv", "contracts/asset-selection-context/v2/state-machine.csv", "contracts/asset-selection-context/v2/source-fingerprints.csv",
    "contracts/asset-selection-context/v3/README.md", "contracts/asset-selection-context/v3/asset-selection-context-contract.md", "contracts/asset-selection-context/v3/capability-matrix.csv", "contracts/asset-selection-context/v3/failure-codes.csv", "contracts/asset-selection-context/v3/state-machine.csv", "contracts/asset-selection-context/v3/source-fingerprints.csv",
    "contracts/portfolio-csv-exchange/v1/README.md", "contracts/portfolio-csv-exchange/v1/portfolio-csv-exchange-contract.md", "contracts/portfolio-csv-exchange/v1/manifest.schema.json", "contracts/portfolio-csv-exchange/v1/import-receipt.schema.json",
    "contracts/portfolio-csv-exchange/v1/handoff-public-preview.schema.json", "contracts/portfolio-csv-exchange/v1/handoff-trusted-preview.schema.json", "contracts/portfolio-csv-exchange/v1/handoff-confirmation.schema.json", "contracts/portfolio-csv-exchange/v1/handoff-attempt.schema.json", "contracts/portfolio-csv-exchange/v1/handoff-result.schema.json", "contracts/portfolio-csv-exchange/v1/handoff-receipt.schema.json",
    "contracts/portfolio-csv-exchange/v1/handoff-recovery-candidates.schema.json", "contracts/portfolio-csv-exchange/v1/handoff-recovery-public-preview.schema.json", "contracts/portfolio-csv-exchange/v1/handoff-recovery-trusted-preview.schema.json", "contracts/portfolio-csv-exchange/v1/handoff-recovery-confirmation.schema.json", "contracts/portfolio-csv-exchange/v1/handoff-recovery-attempt.schema.json",
    "contracts/portfolio-csv-exchange/v1/staged-imports-read-model.schema.json", "contracts/portfolio-csv-exchange/v1/cash-candidates-read-model.schema.json", "contracts/portfolio-csv-exchange/v1/cash-candidate-public.schema.json", "contracts/portfolio-csv-exchange/v1/cash-reviewed-candidate.schema.json",
    "contracts/portfolio-csv-exchange/v1/capability-matrix.csv", "contracts/portfolio-csv-exchange/v1/failure-codes.csv", "contracts/portfolio-csv-exchange/v1/state-machine.csv", "contracts/portfolio-csv-exchange/v1/source-fingerprints.csv",
    
    
    "contracts/provider-mapping-command/v1/README.md", "contracts/provider-mapping-command/v1/provider-mapping-command-contract.md", "contracts/provider-mapping-command/v1/capability-matrix.csv", "contracts/provider-mapping-command/v1/command-types.csv", "contracts/provider-mapping-command/v1/failure-codes.csv", "contracts/provider-mapping-command/v1/state-machine.csv", "contracts/provider-mapping-command/v1/source-fingerprints.csv",
    "contracts/desktop-provider-search/v1/README.md", "contracts/desktop-provider-search/v1/desktop-provider-search-contract.md", "contracts/desktop-provider-search/v1/capability-matrix.csv", "contracts/desktop-provider-search/v1/failure-codes.csv", "contracts/desktop-provider-search/v1/state-machine.csv", "contracts/desktop-provider-search/v1/source-fingerprints.csv",
    "contracts/desktop-provider-probe/v1/README.md", "contracts/desktop-provider-probe/v1/desktop-provider-probe-contract.md", "contracts/desktop-provider-probe/v1/capability-matrix.csv", "contracts/desktop-provider-probe/v1/failure-codes.csv", "contracts/desktop-provider-probe/v1/state-machine.csv", "contracts/desktop-provider-probe/v1/source-fingerprints.csv",
    "contracts/desktop-provider-probe-promotion/v1/README.md", "contracts/desktop-provider-probe-promotion/v1/desktop-provider-probe-promotion-contract.md", "contracts/desktop-provider-probe-promotion/v1/capability-matrix.csv", "contracts/desktop-provider-probe-promotion/v1/failure-codes.csv", "contracts/desktop-provider-probe-promotion/v1/state-machine.csv", "contracts/desktop-provider-probe-promotion/v1/source-fingerprints.csv",
    "contracts/desktop-market-history-plan/v1/README.md", "contracts/desktop-market-history-plan/v1/capability-matrix.csv", "contracts/desktop-market-history-plan/v1/failure-codes.csv", "contracts/desktop-market-history-plan/v1/state-machine.csv", "contracts/desktop-market-history-plan/v1/source-fingerprints.csv",
    "contracts/desktop-market-history-fetch/v1/README.md", "contracts/desktop-market-history-fetch/v1/capability-matrix.csv", "contracts/desktop-market-history-fetch/v1/failure-codes.csv", "contracts/desktop-market-history-fetch/v1/state-machine.csv", "contracts/desktop-market-history-fetch/v1/source-fingerprints.csv",
    "contracts/desktop-fx-demand-coverage/v1/README.md", "contracts/desktop-fx-demand-coverage/v1/failure-codes.csv", "contracts/desktop-fx-demand-coverage/v1/source-fingerprints.csv",
    "contracts/desktop-fx-pair-probe/v1/README.md", "contracts/desktop-fx-pair-probe/v1/failure-codes.csv", "contracts/desktop-fx-pair-probe/v1/source-fingerprints.csv",
    "contracts/desktop-fx-pair-promotion/v1/README.md", "contracts/desktop-fx-pair-promotion/v1/failure-codes.csv", "contracts/desktop-fx-pair-promotion/v1/source-fingerprints.csv",
    "contracts/desktop-fx-history-review/v1/README.md", "contracts/desktop-fx-history-review/v1/failure-codes.csv", "contracts/desktop-fx-history-review/v1/source-fingerprints.csv",
    "apps/data/data_fx_demand_coverage_service_v1.R", "apps/data/data_fx_pair_probe_service_v1.R", "apps/data/data_fx_pair_promotion_service_v1.R", "apps/data/data_fx_history_review_service_v1.R",
    "scripts/desktop_fx_demand_coverage.py", "scripts/desktop_fx_pair_probe.py", "scripts/desktop_fx_pair_promotion.py", "scripts/desktop_fx_history_review.py",
    "migrations/reference/desktop_fx_demand_coverage_v1.py", "migrations/reference/desktop_fx_pair_probe_v1.py", "migrations/reference/desktop_fx_pair_promotion_v1.py", "migrations/reference/desktop_fx_history_review_v1.py",
    "contracts/desktop-fx-pair-promotion/v1/yahoo-provider-manifest.json", "docs/decisions/ADR-177-on-demand-fx-history-and-non-authoritative-presentation-projection.md",
    "contracts/market-calendar/v1/README.md", "contracts/market-calendar/v1/failure-codes.csv", "contracts/market-calendar/v1/source-fingerprints.csv", "docs/decisions/ADR-178-versioned-listing-and-fx-pair-calendar-profiles.md", "migrations/reference/market_calendar_v1.py", "migrations/reference/market_calendar_registry_v1.py", "migrations/reference/desktop_market_calendar_gap_catalog_v1.py", "migrations/reference/market_calendar_correction_v1.py", "migrations/reference/desktop_calendar_gap_review_v1.py", "scripts/desktop_market_calendar_gap_catalog.py", "scripts/desktop_calendar_gap_review.py", "apps/data/data_market_calendar_gap_service_v1.R", "apps/data/data_calendar_gap_review_service_v1.R",
    "contracts/reward-valuation/v1/README.md", "contracts/reward-valuation/v1/failure-codes.csv", "contracts/reward-valuation/v1/source-fingerprints.csv", "docs/decisions/ADR-179-provider-neutral-reward-valuation-evidence.md", "docs/decisions/ADR-180-statement-reward-canonical-finalization-and-standard-workflow.md", "migrations/reference/reward_valuation_v1.py", "migrations/reference/desktop_reward_daily_close_v1.py", "scripts/desktop_reward_daily_close.py", "apps/data/data_reward_daily_close_service_v1.R",
    "migrations/reference/cash_coverage_v1.py",
    "migrations/reference/asset_activity_v1.py", "migrations/reference/legacy_per_asset_trade_planner_v1.py",
    "migrations/reference/legacy_asset_companion_v1.py",
    "migrations/reference/per_asset_sandbox_apply_v1.py",
    "migrations/reference/realized_tax_projection_v1.py", "migrations/reference/realized_materialization_v1.py",
    "migrations/reference/tax_model_plugin_v1.py", "migrations/reference/tax_model_plugin_v2.py",
    "migrations/reference/de_personal_income_tax_projection_v2.py", "migrations/reference/realized_tax_projection_v2.py", "migrations/reference/realized_group_projection_v1.py",
    "migrations/reference/unrealized_valuation_v1.py", "migrations/reference/fx_history_v1.py",
    "migrations/reference/daily_market_history_v1.py", "migrations/reference/legacy_import_data_command_v1.py",
    "contracts/v2/schema.sql", "contracts/v2.1/migrate-from-v2.sql", "contracts/v2.2/migrate-from-v2.1.sql",
    "contracts/portfolio-ledger/v1/schema.sql", "contracts/portfolio-ledger/v1.1/add-asset-activity-v1.sql", "contracts/portfolio-ledger/v1.1/add-owner-confirmed-source-order-v1.sql", "contracts/portfolio-ledger/v1.1/enable-generic-derivative-activity-v1.sql",
    "contracts/desktop-product-derivative-capability/v1/README.md", "contracts/desktop-product-derivative-capability/v1/desktop-product-derivative-capability-contract.md",
    "contracts/desktop-product-derivative-capability/v1/capability-matrix.csv", "contracts/desktop-product-derivative-capability/v1/failure-codes.csv", "contracts/desktop-product-derivative-capability/v1/state-machine.csv",
    "contracts/desktop-product-derivative-capability/v1/preview.schema.json", "contracts/desktop-product-derivative-capability/v1/confirmation.schema.json", "contracts/desktop-product-derivative-capability/v1/receipt.schema.json", "contracts/desktop-product-derivative-capability/v1/source-fingerprints.csv",
    "docs/decisions/ADR-142-owner-confirmed-generic-derivative-product-capability.md", "docs/decisions/ADR-143-targeted-immutable-generation-recovery.md", "docs/release-notes-v0.2.0-rc.17.md",
    "docs/decisions/ADR-144-immutable-activity-draft-source-generation-supersession.md", "docs/release-notes-v0.2.0-rc.18.md",
    "docs/decisions/ADR-145-mixed-state-activity-draft-source-retirement.md", "docs/release-notes-v0.2.0-rc.19.md",
    "docs/decisions/ADR-146-guided-asset-center-provider-and-tax-handoffs.md", "docs/release-notes-v0.2.0-rc.20.md",
    "docs/decisions/ADR-147-lossless-redundant-portfolio-csv-exchange.md", "docs/release-notes-v0.2.0-rc.21.md", "docs/release-notes-v0.2.0-rc.22.md", "docs/release-notes-v0.2.0-rc.23.md",
    "docs/decisions/ADR-148-explicit-asset-price-currency-revision.md", "docs/release-notes-v0.2.0-rc.24.md",
    "docs/decisions/ADR-149-browser-local-asset-selection-context.md", "docs/release-notes-v0.2.0-rc.25.md",
    "docs/decisions/ADR-150-identity-bearing-browser-asset-refs.md", "docs/release-notes-v0.2.0-rc.26.md",
    "docs/decisions/ADR-151-identity-bearing-account-facets-and-explicit-consumer-domain.md", "docs/release-notes-v0.2.0-rc.27.md",
    "docs/decisions/ADR-152-inclusive-activity-and-fresh-fifo-holding-intervals.md", "docs/release-notes-v0.2.0-rc.28.md",
    "docs/decisions/ADR-153-explicit-browser-null-selection-and-full-filter-reset.md", "docs/release-notes-v0.2.0-rc.29.md",
    "docs/decisions/ADR-154-release-snapshot-transitive-source-closure.md", "docs/release-notes-v0.2.0-rc.30.md",
    "docs/decisions/ADR-170-general-statement-import-mapping-and-deferred-valuation.md", "docs/decisions/ADR-171-context-bound-statement-mapping-profiles-and-draft-handoff.md",
    "docs/decisions/ADR-172-legacy-derived-exchange-reward-adapters-and-bsdex-overlay.md", "docs/decisions/ADR-173-tolerant-statement-preview-and-quiet-identity-boundary.md",
    "docs/decisions/ADR-174-single-confirmation-exchange-reward-activity-draft-handoff.md", "docs/decisions/ADR-175-statement-scoped-provider-neutral-reward-valuation-ui.md", "docs/decisions/ADR-176-trusted-source-indexed-reward-draft-loading.md", "docs/release-notes-v0.2.0-rc.31.md", "docs/release-notes-v0.2.0-rc.32.md", "docs/release-notes-v0.2.0-rc.33.md", "docs/release-notes-v0.2.0-rc.34.md", "docs/release-notes-v0.2.0-rc.35.md", "docs/release-notes-v0.2.0-rc.36.md", "docs/release-notes-v0.2.0-rc.37.md", "docs/release-notes-v0.2.0-rc.38.md", "docs/release-notes-v0.2.0-rc.39.md", "docs/release-notes-v0.2.0-rc.40.md", "docs/release-notes-v0.2.0-rc.41.md", "docs/release-notes-v0.2.0-rc.42.md", "docs/release-notes-v0.2.0-rc.43.md", "docs/release-notes-v0.2.0-rc.44.md", "docs/release-notes-v0.2.0-rc.45.md", "docs/release-notes-v0.2.0-rc.46.md", "docs/release-notes-v0.2.0-rc.47.md", "docs/release-notes-v0.2.0-rc.48.md", "docs/release-notes-v0.2.0-rc.49.md", "docs/release-notes-v0.2.0-rc.50.md", "docs/release-notes-v0.2.0-rc.51.md", "docs/release-notes-v0.2.0-rc.52.md", "docs/release-notes-v0.2.0-rc.53.md", "docs/release-notes-v0.2.0-rc.54.md", "docs/release-notes-v0.2.0-rc.55.md", "docs/release-notes-v0.2.0-rc.56.md", "docs/release-notes-v0.2.0-rc.57.md", "docs/release-notes-v0.2.0-rc.58.md", "docs/release-notes-v0.2.0-rc.59.md", "docs/release-notes-v0.2.0-rc.60.md", "docs/release-notes-v0.2.0-rc.61.md", "docs/release-notes-v0.2.0-rc.62.md", "docs/decisions/ADR-181-atomic-statement-reward-collision-recovery.md", "docs/release-notes-v0.2.0-rc.63.md", "docs/release-notes-v0.2.0-rc.64.md", "docs/release-notes-v0.2.0-rc.65.md", "docs/release-notes-v0.2.0-rc.66.md", "docs/release-notes-v0.2.0-rc.67.md", "docs/release-notes-v0.2.0-rc.68.md", "docs/release-notes-v0.2.0-rc.69.md", "docs/release-notes-v0.2.0-rc.70.md", "docs/release-notes-v0.2.0-rc.71.md", "docs/release-notes-v0.2.0-rc.72.md", "docs/release-notes-v0.2.0-rc.73.md",
    "docs/decisions/ADR-159-immutable-cash-coverage-revisions-and-schema2901.md", "docs/decisions/ADR-160-separate-portfolio-csv-domain-handoffs.md", "docs/decisions/ADR-161-synthetic-read-only-statement-review-boundary.md", "docs/cash-coverage-schema2901-migration.md",
    "contracts/desktop-product-asset-activity/v1/README.md",
    "contracts/desktop-product-asset-activity/v1/desktop-product-asset-activity-contract.md",
    "contracts/desktop-product-asset-activity/v1/preview.schema.json",
    "contracts/desktop-product-asset-activity/v1/generation-manifest.schema.json",
    "contracts/desktop-product-asset-activity/v1/result.schema.json",
    "contracts/desktop-product-asset-activity/v1/failure-codes.csv",
    "contracts/desktop-product-asset-activity/v1/state-machine.csv",
    "contracts/desktop-product-asset-activity/v1/capability-matrix.csv",
    "contracts/desktop-product-asset-activity/v1/source-fingerprints.csv",
    "contracts/desktop-product-asset-activity/v1.1/README.md",
    "contracts/desktop-product-asset-activity/v1.1/native-preview.schema.json",
    "contracts/desktop-product-asset-activity/v1.1/source-fingerprints.csv",
    "contracts/desktop-product-asset-activity/v2/README.md",
    "contracts/desktop-product-asset-activity/v2/read-model.schema.json",
    "contracts/desktop-product-asset-activity/v2/capability-matrix.csv",
    "contracts/desktop-product-asset-activity/v2/source-fingerprints.csv",
    "contracts/desktop-product-asset-activity/v3/README.md",
    "contracts/desktop-product-asset-activity/v3/read-model.schema.json",
    "contracts/desktop-product-asset-activity/v3/capability-matrix.csv",
    "contracts/desktop-product-asset-activity/v3/source-fingerprints.csv",
    "contracts/desktop-product-asset-activity/v4/README.md",
    "contracts/desktop-product-asset-activity/v4/read-model.schema.json",
    "contracts/desktop-product-asset-activity/v4/capability-matrix.csv",
    "contracts/desktop-product-asset-activity/v4/source-fingerprints.csv",
    "contracts/desktop-product-asset-activity/v5/README.md",
    "contracts/desktop-product-asset-activity/v5/read-model.schema.json",
    "contracts/desktop-product-asset-activity/v5/capability-matrix.csv",
    "contracts/desktop-product-asset-activity/v5/source-fingerprints.csv",
    "contracts/desktop-product-activity-draft/v1/README.md",
    "contracts/desktop-product-activity-draft/v1/desktop-activity-draft-contract.md",
    "contracts/desktop-product-activity-draft/v1/capability-matrix.csv",
    "contracts/desktop-product-activity-draft/v1/state-machine.csv",
    "contracts/desktop-product-activity-draft/v1/failure-codes.csv",
    "contracts/desktop-product-activity-draft/v1/draft.schema.json",
    "contracts/desktop-product-activity-draft/v1/public-draft.schema.json",
    "contracts/desktop-product-activity-draft/v1/mapping-profile.schema.json",
    "contracts/desktop-product-activity-draft/v1/public-mapping-profile.schema.json",
    "contracts/desktop-product-activity-draft/v1/confirmation.schema.json",
    "contracts/desktop-product-activity-draft/v1/attempt.schema.json",
    "contracts/desktop-product-activity-draft/v1/receipt.schema.json",
    "contracts/desktop-product-activity-draft/v1/mixed-source-retirement-attempt.schema.json",
    "contracts/desktop-product-activity-draft/v1/mixed-source-retirement-confirmation.schema.json",
    "contracts/desktop-product-activity-draft/v1/mixed-source-retirement-preview.schema.json",
    "contracts/desktop-product-activity-draft/v1/mixed-source-retirement-trusted-preview.schema.json",
    "contracts/desktop-product-activity-draft/v1/mixed-source-retirement-writer-barrier.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-active.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-attempt.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-boundaries.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-confirmation.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-generation.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-preview.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-receipt.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-state.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-trusted-preview.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-writer-barrier.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-fingerprints.csv",
    "contracts/desktop-product-asset-quantity-scale/v1/README.md",
    "contracts/desktop-product-asset-quantity-scale/v1/desktop-asset-quantity-scale-contract.md",
    "contracts/desktop-product-asset-quantity-scale/v1/capability-matrix.csv",
    "contracts/desktop-product-asset-quantity-scale/v1/state-machine.csv",
    "contracts/desktop-product-asset-quantity-scale/v1/failure-codes.csv",
    "contracts/desktop-product-asset-quantity-scale/v1/public-preview.schema.json",
    "contracts/desktop-product-asset-quantity-scale/v1/confirmation.schema.json",
    "contracts/desktop-product-asset-quantity-scale/v1/attempt.schema.json",
    "contracts/desktop-product-asset-quantity-scale/v1/receipt.schema.json",
    "contracts/desktop-product-asset-quantity-scale/v1/source-fingerprints.csv",
    "fixtures/product/legacy-per-asset-review-v1/invented_asset_trades.csv",
    "fixtures/product/legacy-per-asset-review-v1/invented_assets.csv",
    "contracts/realized-event-tax/v1/schema.sql", "contracts/realized-group-projection/v1/schema.sql",
    "contracts/tax-model-plugin/v1/schema.sql", "contracts/tax-ui/v1/migrate-tax-plugin-store-v1900-to-v2200.sql", "contracts/tax-ui/v1/migrate-tax-plugin-store-v2200-to-v2201.sql", "contracts/tax-ui/v1/source-fingerprints.csv",
    "contracts/tax-plugins/de-personal-income-tax-v2/completed-projection.schema.json", "contracts/tax-plugins/de-personal-income-tax-v2/classification-definitions.csv", "contracts/tax-plugins/de-personal-income-tax-v2/parameter-definitions.csv", "contracts/unrealized-valuation/v1/schema.sql",
    "contracts/fx-history/v1/schema.sql", "contracts/daily-market-history/v1/schema.sql", "contracts/daily-market-history/v1/migrate-store-v2300-to-v2400.sql",
    "contracts/trade-analysis/v1/metric-definitions.csv", "contracts/market-analysis/v1/metric-definitions.csv",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v1/manifest.json",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v1/plugin.R",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v1/classification-definitions.csv",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v1/parameter-definitions.csv",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v1/rule-matrix.csv",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v1/legal-references.csv",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v2/manifest.json",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v2/plugin.R",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v2/classification-definitions.csv",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v2/parameter-definitions.csv",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v2/rule-matrix.csv",
    "plugins/tax_models/tax_de_personal_income_tax_projection_v2/legal-references.csv",
    "workers/tax_plugin_sandbox_v1.py", "contracts/desktop-product/v1/desktop-product-contract.md"
  )
  package_files <- unlist(lapply(file.path(project_root, "packages", c("spotcore", "spotdisplay")), function(root) {
    list.files(root, recursive = TRUE, full.names = TRUE, all.files = FALSE, include.dirs = FALSE)
  }))
  package_sources <- substring(package_files, nchar(project_root, type = "bytes") + 2L)
  declared_package_sources <- rows$path[startsWith(rows$path, "packages/spotcore/") |
    startsWith(rows$path, "packages/spotdisplay/")]
  if (!setequal(package_sources, declared_package_sources)) {
    .desktop_product_abort_v1("desktop_product_project_invalid")
  }
  if (isTRUE(enforce_current_scope)) {
    actual_install_sources <- c(package_sources, fixed)
    declared_install_sources <- rows$path[rows$path %in% c(declared_package_sources, fixed)]
    if (!setequal(actual_install_sources, declared_install_sources)) {
      .desktop_product_abort_v1("desktop_product_project_invalid")
    }
  } else {
    bound_required <- c(
      "VERSION", "packages/spotcore/DESCRIPTION", "packages/spotcore/NAMESPACE",
      "packages/spotdisplay/DESCRIPTION", "packages/spotdisplay/NAMESPACE",
      "scripts/portelyra_desktop.R", "apps/data/desktop_product_app_v1.R",
      "apps/shared/portelyra_ui_shell.R", "contracts/v2/schema.sql",
      "contracts/v2.1/migrate-from-v2.sql", "contracts/desktop-product/v1/desktop-product-contract.md"
    )
    if (!all(bound_required %in% rows$path)) .desktop_product_abort_v1("desktop_product_project_invalid")
    bound_files <- list.files(
      project_root, recursive = TRUE, full.names = TRUE, all.files = TRUE,
      include.dirs = FALSE, no.. = TRUE
    )
    bound_relative <- substring(bound_files, nchar(project_root, type = "bytes") + 2L)
    expected_bound <- unique(c("AGENTS.md", "contracts/desktop-product/v1/source-fingerprints.csv", rows$path))
    if (!setequal(bound_relative, expected_bound)) .desktop_product_abort_v1("desktop_product_project_invalid")
  }
  for (index in seq_len(nrow(rows))) {
    path <- file.path(project_root, rows$path[[index]])
    if (!file.exists(path) || dir.exists(path) || .desktop_product_symlink_v1(path) ||
        !identical(digest::digest(file = path, algo = "sha256", serialize = FALSE), rows$sha256[[index]])) {
      .desktop_product_abort_v1("desktop_product_project_invalid")
    }
  }
  closure_sources <- c(
    "scripts/desktop_release_source_closure.py",
    "workers/reference/desktop_release_source_closure_v1.py"
  )
  closure_declared <- closure_sources %in% rows$path
  if (any(closure_declared) && !all(closure_declared)) .desktop_product_abort_v1("desktop_product_project_invalid")
  if (all(closure_declared)) {
    python <- Sys.which("python3")
    output <- if (nzchar(python)) suppressWarnings(system2(
      python,
      c("-B", "-E", "-s", shQuote(file.path(project_root, closure_sources[[1L]])), "--project-root", shQuote(project_root)),
      stdout = TRUE, stderr = TRUE, env = c("PYTHONDONTWRITEBYTECODE=1")
    )) else structure(character(), status = 1L)
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    if (!identical(as.integer(status), 0L) || !identical(output, '{"status":"complete"}')) {
      .desktop_product_abort_v1("desktop_product_project_invalid")
    }
  }
  invisible(rows)
}

.desktop_product_source_fingerprint_v1 <- function(project_root, enforce_current_scope = TRUE) {
  invisible(.desktop_product_verify_source_registry_v1(project_root, enforce_current_scope = enforce_current_scope))
  roots <- file.path(project_root, "packages", c("spotcore", "spotdisplay"))
  fixed <- file.path(project_root, c(
    "scripts/portelyra_desktop.R", "apps/data/desktop_product_app_v1.R",
    "apps/shared/portelyra_ui_shell.R", "contracts/v2/schema.sql",
    "contracts/v2.1/migrate-from-v2.sql", "contracts/desktop-product/v1/desktop-product-contract.md",
    "contracts/desktop-product/v1/source-fingerprints.csv"
  ))
  files <- sort(c(unlist(lapply(roots, function(root) {
    list.files(root, recursive = TRUE, full.names = TRUE, all.files = FALSE, include.dirs = FALSE)
  })), fixed), method = "radix")
  if (!length(files) || any(vapply(files, .desktop_product_symlink_v1, logical(1)))) {
    .desktop_product_abort_v1("desktop_product_project_invalid")
  }
  relative <- substring(files, nchar(project_root, type = "bytes") + 2L)
  hashes <- vapply(files, function(path) digest::digest(file = path, algo = "sha256", serialize = FALSE), character(1))
  material <- paste(relative, hashes, sep = "=", collapse = "\n")
  digest::digest(charToRaw(enc2utf8(material)), algo = "sha256", serialize = FALSE)
}

.desktop_product_json_write_atomic_v1 <- function(path, value) {
  old_umask <- Sys.umask("0077")
  on.exit(Sys.umask(old_umask), add = TRUE)
  parent <- dirname(path)
  if (!dir.exists(parent) || .desktop_product_symlink_v1(parent) || .desktop_product_symlink_v1(path)) {
    .desktop_product_abort_v1("desktop_product_symlink_rejected")
  }
  temporary <- tempfile(pattern = paste0(".", basename(path), ".tmp-"), tmpdir = parent)
  on.exit(if (file.exists(temporary)) unlink(temporary, force = TRUE), add = TRUE)
  bytes <- charToRaw(enc2utf8(as.character(jsonlite::toJSON(
    value, auto_unbox = TRUE, null = "null", na = "null", digits = NA, pretty = FALSE
  ))))
  connection <- file(temporary, open = "wb")
  writeBin(bytes, connection)
  close(connection)
  suppressWarnings(Sys.chmod(temporary, mode = "0600"))
  if (!.desktop_product_owner_mode_v1(temporary)) .desktop_product_abort_v1("desktop_product_permissions_invalid")
  if (file.exists(path) || dir.exists(path)) .desktop_product_abort_v1("desktop_product_registry_conflict")
  if (!file.rename(temporary, path)) .desktop_product_abort_v1("desktop_product_registry_conflict")
  suppressWarnings(Sys.chmod(path, mode = "0600"))
  if (!.desktop_product_owner_mode_v1(path)) .desktop_product_abort_v1("desktop_product_permissions_invalid")
  invisible(path)
}

.desktop_product_json_read_v1 <- function(path, code = "desktop_product_registry_invalid") {
  if (!file.exists(path) || dir.exists(path) || .desktop_product_symlink_v1(path) || !.desktop_product_owner_mode_v1(path)) {
    .desktop_product_abort_v1(code)
  }
  size <- suppressWarnings(file.info(path)$size)
  if (length(size) != 1L || is.na(size) || size < 2 || size > 1048576) .desktop_product_abort_v1(code)
  value <- tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(error) NULL)
  if (is.null(value) || !is.list(value)) .desktop_product_abort_v1(code)
  value
}

.desktop_product_random_id_v1 <- function(prefix) {
  bytes <- openssl::rand_bytes(16L)
  paste0(prefix, paste(format(bytes), collapse = ""))
}

.desktop_product_process_start_v1 <- function(pid = Sys.getpid()) {
  if (!is.numeric(pid) || length(pid) != 1L || is.na(pid) || pid < 1 || pid != floor(pid)) return(NULL)
  path <- file.path("/proc", as.character(as.integer(pid)), "stat")
  line <- suppressWarnings(tryCatch(readLines(path, warn = FALSE, n = 1L), error = function(error) character()))
  if (length(line) != 1L) return(NULL)
  positions <- gregexpr(") ", line, fixed = TRUE)[[1L]]
  positions <- positions[positions > 0L]
  if (!length(positions)) return(NULL)
  close <- positions[[length(positions)]]
  fields <- strsplit(substring(line, close + 2L), " ", fixed = TRUE)[[1L]]
  if (length(fields) < 20L || !grepl("^[0-9]+$", fields[[20L]])) return(NULL)
  fields[[20L]]
}

.desktop_product_lock_owner_v1 <- function() {
  start <- .desktop_product_process_start_v1()
  if (is.null(start)) .desktop_product_abort_v1("desktop_product_platform_unsupported")
  list(
    contract_version = 1L,
    pid = as.integer(Sys.getpid()),
    process_start = start,
    nonce = .desktop_product_random_id_v1("lck_")
  )
}

.desktop_product_lock_owner_valid_v1 <- function(owner) {
  is.list(owner) && identical(names(owner), c("contract_version", "pid", "process_start", "nonce")) &&
    identical(owner$contract_version, 1L) && is.numeric(owner$pid) && length(owner$pid) == 1L &&
    !is.na(owner$pid) && owner$pid >= 1 && owner$pid == floor(owner$pid) &&
    is.character(owner$process_start) && length(owner$process_start) == 1L && grepl("^[0-9]+$", owner$process_start) &&
    is.character(owner$nonce) && length(owner$nonce) == 1L && grepl("^lck_[a-f0-9]{32}$", owner$nonce)
}

.desktop_product_lock_active_v1 <- function(owner) {
  .desktop_product_lock_owner_valid_v1(owner) &&
    identical(.desktop_product_process_start_v1(as.integer(owner$pid)), owner$process_start)
}

.desktop_product_acquire_lock_v1 <- function(path, conflict_code) {
  old_umask <- Sys.umask("0077")
  on.exit(Sys.umask(old_umask), add = TRUE)
  if (!conflict_code %in% desktop_product_error_codes_v1()) .desktop_product_abort_v1("desktop_product_boundary_failed")
  if (.desktop_product_symlink_v1(path) || (file.exists(path) && !dir.exists(path))) .desktop_product_abort_v1(conflict_code)
  if (dir.exists(path)) {
    owner_path <- file.path(path, "owner.json")
    if (.desktop_product_symlink_v1(owner_path)) .desktop_product_abort_v1(conflict_code)
    owner <- tryCatch(jsonlite::fromJSON(owner_path, simplifyVector = FALSE), error = function(error) NULL)
    if (.desktop_product_lock_active_v1(owner)) .desktop_product_abort_v1(conflict_code)
    stale <- paste0(path, ".stale-", paste(format(openssl::rand_bytes(8L)), collapse = ""))
    if (!file.rename(path, stale)) .desktop_product_abort_v1(conflict_code)
    unlink(stale, recursive = TRUE, force = TRUE)
    if (dir.exists(stale) || file.exists(stale)) .desktop_product_abort_v1(conflict_code)
  }
  if (!dir.create(path, mode = "0700", showWarnings = FALSE)) .desktop_product_abort_v1(conflict_code)
  suppressWarnings(Sys.chmod(path, mode = "0700"))
  owner <- .desktop_product_lock_owner_v1()
  .desktop_product_json_write_atomic_v1(file.path(path, "owner.json"), owner)
  owner
}

.desktop_product_release_lock_v1 <- function(path, owner) {
  owner_path <- file.path(path, "owner.json")
  if (.desktop_product_symlink_v1(owner_path)) .desktop_product_abort_v1("desktop_product_boundary_failed")
  current <- tryCatch(jsonlite::fromJSON(owner_path, simplifyVector = FALSE), error = function(error) NULL)
  if (!.desktop_product_lock_owner_valid_v1(current) || !identical(current$nonce, owner$nonce)) {
    .desktop_product_abort_v1("desktop_product_boundary_failed")
  }
  unlink(path, recursive = TRUE, force = TRUE)
  if (dir.exists(path) || file.exists(path)) .desktop_product_abort_v1("desktop_product_boundary_failed")
  invisible(TRUE)
}

.desktop_product_version_v1 <- function(project_root) {
  path <- file.path(project_root, "VERSION")
  if (!file.exists(path) || dir.exists(path) || .desktop_product_symlink_v1(path)) {
    .desktop_product_abort_v1("desktop_product_release_version_invalid")
  }
  value <- tryCatch(readLines(path, warn = FALSE, encoding = "UTF-8"), error = function(error) character())
  if (length(value) != 1L || !grepl("^[0-9]+[.][0-9]+[.][0-9]+(-rc[.][0-9]+)?$", value[[1L]])) {
    .desktop_product_abort_v1("desktop_product_release_version_invalid")
  }
  package_version <- sub("-rc[.][0-9]+$", "", value[[1L]])
  for (package in c("spotcore", "spotdisplay")) {
    description <- file.path(project_root, "packages", package, "DESCRIPTION")
    fields <- tryCatch(read.dcf(description, fields = "Version"), error = function(error) NULL)
    if (is.null(fields) || length(fields) != 1L || !identical(unname(fields[[1L]]), package_version)) {
      .desktop_product_abort_v1("desktop_product_release_version_invalid")
    }
  }
  value[[1L]]
}

.desktop_product_version_newer_v1 <- function(candidate, current) {
  key <- function(value) {
    match <- regexec("^([0-9]+)[.]([0-9]+)[.]([0-9]+)(?:-rc[.]([0-9]+))?$", value, perl = TRUE)
    parts <- regmatches(value, match)[[1L]]
    if (length(parts) != 5L) return(NULL)
    rc <- suppressWarnings(as.integer(parts[[5L]]))
    c(as.numeric(parts[2:4]), if (is.na(rc)) 1 else 0, if (is.na(rc)) 0 else rc)
  }
  candidate_key <- key(candidate); current_key <- key(current)
  if (is.null(candidate_key) || is.null(current_key)) return(FALSE)
  difference <- which(candidate_key != current_key)
  length(difference) > 0L && candidate_key[[difference[[1L]]]] > current_key[[difference[[1L]]]]
}

.desktop_product_manifest_valid_v1 <- function(value, expected_fingerprint = NULL) {
  valid <- is.list(value) && identical(names(value), c("contract_version", "product_version", "source_fingerprint", "packages")) &&
    identical(value$contract_version, 2L) && is.character(value$product_version) && length(value$product_version) == 1L &&
    grepl("^[0-9]+[.][0-9]+[.][0-9]+(-rc[.][0-9]+)?$", value$product_version) &&
    is.character(value$source_fingerprint) && length(value$source_fingerprint) == 1L &&
    grepl("^[a-f0-9]{64}$", value$source_fingerprint) && is.list(value$packages) &&
    identical(unlist(value$packages, use.names = FALSE), c("spotcore", "spotdisplay"))
  isTRUE(valid) && (is.null(expected_fingerprint) || identical(value$source_fingerprint, expected_fingerprint))
}

.desktop_product_install_manifest_v1 <- function(project_root, source_fingerprint) list(
  contract_version = 2L, product_version = .desktop_product_version_v1(project_root),
  source_fingerprint = source_fingerprint, packages = list("spotcore", "spotdisplay")
)

desktop_product_preflight_v1 <- function(project_root, home = desktop_product_default_home_v1()) {
  .desktop_product_boundary_v1({
    if (!identical(Sys.info()[["sysname"]], "Linux") || !Sys.info()[["machine"]] %in% c("x86_64", "amd64")) {
      .desktop_product_abort_v1("desktop_product_platform_unsupported")
    }
    if (getRversion() < "4.2.0") .desktop_product_abort_v1("desktop_product_dependency_missing")
    dependencies <- c(DBI = "1.2.0", digest = "0.6.30", jsonlite = "1.8.0", openssl = "2.0.0", RSQLite = "2.3.0", shiny = "1.8.0")
    if (!all(vapply(names(dependencies), function(package) {
      requireNamespace(package, quietly = TRUE) && utils::packageVersion(package) >= base::package_version(dependencies[[package]])
    }, logical(1)))) .desktop_product_abort_v1("desktop_product_dependency_missing")
    python <- suppressWarnings(system2("python3", "--version", stdout = TRUE, stderr = TRUE))
    python_version <- if (length(python) == 1L && is.null(attr(python, "status")) && grepl("^Python [0-9]+[.][0-9]+[.][0-9]+", python)) {
      sub("^Python ([0-9]+[.][0-9]+[.][0-9]+).*$", "\\1", python)
    } else "0.0.0"
    if (base::package_version(python_version) < base::package_version("3.10.0")) .desktop_product_abort_v1("desktop_product_dependency_missing")
    root <- .desktop_product_project_v1(project_root)
    if (!.desktop_product_absolute_v1(home)) .desktop_product_abort_v1("desktop_product_home_invalid")
    expanded_home <- path.expand(home)
    .desktop_product_assert_no_symlink_v1(expanded_home)
    if (file.exists(expanded_home) && !dir.exists(expanded_home)) .desktop_product_abort_v1("desktop_product_home_invalid")
    if (dir.exists(expanded_home) && !.desktop_product_owner_mode_v1(expanded_home, directory = TRUE)) {
      .desktop_product_abort_v1("desktop_product_permissions_invalid")
    }
    ancestor <- .desktop_product_normalize_existing_v1(.desktop_product_existing_ancestor_v1(expanded_home))
    if (!dir.exists(ancestor) || file.access(ancestor, 2L) != 0L) .desktop_product_abort_v1("desktop_product_home_invalid")
    comparable_home <- if (dir.exists(expanded_home)) .desktop_product_normalize_existing_v1(expanded_home) else {
      normalizePath(expanded_home, winslash = "/", mustWork = FALSE)
    }
    # Ausnahme (#489, rc.429): die installierte Kopie dieses Homes (<home>/library/.portelyra-source). Sie liegt mit Absicht im Home, und
    # aus ihr laufen Update, Preflight und Start ohne Projektordner. Jeder andere Programmordner im Home (oder umgekehrt) bleibt verboten.
    snapshot <- file.path(comparable_home, "library", ".portelyra-source")
    own_snapshot <- dir.exists(snapshot) && !.desktop_product_symlink_v1(snapshot) &&
      identical(root, .desktop_product_normalize_existing_v1(snapshot))
    if (!own_snapshot && (.desktop_product_is_within_v1(comparable_home, root) || .desktop_product_is_within_v1(root, comparable_home))) {
      .desktop_product_abort_v1("desktop_product_home_inside_project")
    }
    paths <- .desktop_product_home_paths_v1(comparable_home)
    fingerprint <- .desktop_product_source_fingerprint_v1(root)
    installed <- FALSE
    source_current <- FALSE
    if (file.exists(paths$install_manifest)) {
      manifest <- .desktop_product_json_read_v1(paths$install_manifest, "desktop_product_install_conflict")
      installed <- .desktop_product_manifest_valid_v1(manifest) && isTRUE(tryCatch({
        .desktop_product_library_manifest_v1(paths$library)
        TRUE
      }, error = function(error) FALSE))
      if (!installed) .desktop_product_abort_v1("desktop_product_install_conflict")
      source_current <- identical(manifest$source_fingerprint, fingerprint)
    } else if (dir.exists(paths$library) && length(list.files(paths$library, all.files = TRUE, no.. = TRUE))) {
      .desktop_product_abort_v1("desktop_product_install_conflict")
    }
    recovery_required <- file.exists(paths$upgrade_journal)
    if (recovery_required && (dir.exists(paths$upgrade_journal) || .desktop_product_symlink_v1(paths$upgrade_journal))) {
      .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    }
    initialized <- file.exists(paths$registry)
    # Passwortschutz (#535): Gesperrt ist der Datenbestand nicht lesbar; die Laufzeit prueft der Start erst nach dem Entsperren (sonst
    # kaeme die Startseite „Portelyra entsperren“ nie). Wer danach liest, bricht gesperrt mit desktop_product_locked ab.
    if (initialized && !isTRUE(paths$locked)) invisible(desktop_product_runtime_load_v1(comparable_home))
    list(
      desktop_product_preflight_version = 1L,
      status = if (recovery_required) "upgrade_recovery_required" else if (!installed) "ready_to_install" else if (!source_current) "upgrade_required" else if (!initialized) "ready_to_initialize" else "ready_to_start",
      checks = list(
        linux = TRUE, linux_x86_64 = TRUE, r_runtime = TRUE, python_runtime = TRUE, sqlite_runtime = TRUE,
        required_r_packages = TRUE, project_sources = TRUE, home_boundary = TRUE,
        local_packages_installed = installed, release_source_current = source_current,
        upgrade_recovery_required = recovery_required, runtime_registry_initialized = initialized
      ),
      provider_access = FALSE,
      canonical_write = FALSE
    )
  })
}

# enforce_current_scope = FALSE (#571, rc.433): Ein Update aus einem gepruefen Archiv bindet den neuen Stand nur an SEINE eigene, mitsignierte
# Dateiliste, nicht an die eingebaute dieses (aelteren) Codes - sonst haelt jede verschobene Datei alle aelteren Installationen auf.
.desktop_product_install_source_snapshot_v1 <- function(project_root, destination, enforce_current_scope = TRUE) {
  rows <- .desktop_product_verify_source_registry_v1(project_root, enforce_current_scope = enforce_current_scope)
  relative_paths <- sort(unique(c(
    "AGENTS.md", "VERSION", "contracts/desktop-product/v1/source-fingerprints.csv", rows$path
  )), method = "radix")
  snapshot <- file.path(destination, ".portelyra-source")
  .desktop_product_enforce_dir_v1(snapshot)
  for (relative in relative_paths) {
    source <- file.path(project_root, relative); target <- file.path(snapshot, relative)
    directory <- snapshot
    parent_parts <- strsplit(dirname(relative), "/", fixed = TRUE)[[1L]]
    for (part in parent_parts[parent_parts != "."]) {
      directory <- file.path(directory, part)
      .desktop_product_enforce_dir_v1(directory)
    }
    if (!file.copy(source, target, overwrite = FALSE, copy.mode = FALSE, copy.date = FALSE)) {
      .desktop_product_abort_v1("desktop_product_install_failed")
    }
    suppressWarnings(Sys.chmod(target, mode = "0600"))
    if (!.desktop_product_owner_mode_v1(target)) .desktop_product_abort_v1("desktop_product_permissions_invalid")
  }
  if (!identical(.desktop_product_source_fingerprint_v1(snapshot, enforce_current_scope = enforce_current_scope),
                 .desktop_product_source_fingerprint_v1(project_root, enforce_current_scope = enforce_current_scope))) {
    .desktop_product_abort_v1("desktop_product_install_failed")
  }
  invisible(snapshot)
}

.desktop_product_install_packages_v1 <- function(project_root, destination, enforce_current_scope = TRUE) {
  if (dir.exists(destination) || file.exists(destination)) .desktop_product_abort_v1("desktop_product_install_conflict")
  if (!dir.create(destination, mode = "0700", showWarnings = FALSE)) .desktop_product_abort_v1("desktop_product_install_failed")
  suppressWarnings(Sys.chmod(destination, mode = "0700"))
  r_binary <- file.path(R.home("bin"), "R")
  for (package in c("spotcore", "spotdisplay")) {
    output <- suppressWarnings(system2(
      r_binary,
      c("CMD", "INSTALL", "--no-multiarch", "--with-keep.source", "-l", shQuote(destination), shQuote(file.path(project_root, "packages", package))),
      stdout = TRUE, stderr = TRUE
    ))
    if (!is.null(attr(output, "status")) || !dir.exists(file.path(destination, package))) {
      .desktop_product_abort_v1("desktop_product_install_failed")
    }
  }
  .desktop_product_install_source_snapshot_v1(project_root, destination, enforce_current_scope = enforce_current_scope)
  invisible(destination)
}

desktop_product_install_v1 <- function(project_root, home = desktop_product_default_home_v1(), confirmation) {
  .desktop_product_boundary_v1({
    old_umask <- Sys.umask("0077")
    on.exit(Sys.umask(old_umask), add = TRUE)
    if (!identical(confirmation, "INSTALL_LOCAL_RUNTIME")) {
      .desktop_product_abort_v1("desktop_product_install_confirmation_required")
    }
    root <- .desktop_product_project_v1(project_root)
    home <- .desktop_product_ensure_home_v1(home)
    paths <- .desktop_product_home_paths_v1(home)
    fingerprint <- .desktop_product_source_fingerprint_v1(root)
    if (file.exists(paths$install_manifest)) {
      manifest <- .desktop_product_json_read_v1(paths$install_manifest, "desktop_product_install_conflict")
      if (.desktop_product_manifest_valid_v1(manifest, fingerprint) && isTRUE(tryCatch({
        .desktop_product_library_manifest_v1(paths$library, fingerprint)
        TRUE
      }, error = function(error) FALSE))) return(list(status = "already_installed", package_count = 2L))
      .desktop_product_abort_v1("desktop_product_install_conflict")
    }
    if (dir.exists(paths$library) && !length(list.files(paths$library, all.files = TRUE, no.. = TRUE))) {
      unlink(paths$library, recursive = TRUE, force = TRUE)
    }
    if (dir.exists(paths$library) || file.exists(paths$library)) .desktop_product_abort_v1("desktop_product_install_conflict")
    lock <- file.path(home, "desktop-install.lock")
    lock_owner <- .desktop_product_acquire_lock_v1(lock, "desktop_product_install_conflict")
    on.exit(if (dir.exists(lock)) .desktop_product_release_lock_v1(lock, lock_owner), add = TRUE)
    staging <- file.path(home, ".desktop-library-staging")
    if (dir.exists(staging)) {
      if (.desktop_product_symlink_v1(staging)) .desktop_product_abort_v1("desktop_product_install_conflict")
      unlink(staging, recursive = TRUE, force = TRUE)
    } else if (file.exists(staging)) .desktop_product_abort_v1("desktop_product_install_conflict")
    on.exit(if (dir.exists(staging)) unlink(staging, recursive = TRUE, force = TRUE), add = TRUE)
    .desktop_product_install_packages_v1(root, staging)
    manifest <- .desktop_product_install_manifest_v1(root, fingerprint)
    .desktop_product_json_write_atomic_v1(file.path(staging, ".portelyra-install.json"), manifest)
    if (!file.rename(staging, paths$library)) .desktop_product_abort_v1("desktop_product_install_failed")
    list(status = "installed", package_count = 2L)
  }, fallback = "desktop_product_install_failed")
}

.desktop_product_registry_valid_v1 <- function(value) {
  if (!is.list(value) || !identical(names(value), c(
    "contract_version", "runtime_mode", "registry_revision", "tenant_id", "user_id",
    "active_data_space_id", "data_spaces", "created_at_utc"
  ))) return(FALSE)
  if (!identical(value$contract_version, 1L) || !identical(value$runtime_mode, "desktop_product") ||
      !identical(value$registry_revision, 1L) || !is.character(value$tenant_id) || length(value$tenant_id) != 1L ||
      !grepl("^ten_[a-f0-9]{32}$", value$tenant_id) || !is.character(value$user_id) || length(value$user_id) != 1L ||
      !grepl("^usr_[a-f0-9]{32}$", value$user_id) || !is.character(value$active_data_space_id) ||
      length(value$active_data_space_id) != 1L || !grepl("^sbx_[a-f0-9]{32}$", value$active_data_space_id) ||
      !.desktop_product_utc_valid_v1(value$created_at_utc) ||
      !is.list(value$data_spaces) || length(value$data_spaces) != 1L) return(FALSE)
  space <- value$data_spaces[[1L]]
  is.list(space) && identical(names(space), c("data_space_id", "display_label", "status", "created_at_utc")) &&
    identical(space$data_space_id, value$active_data_space_id) && .desktop_product_label_valid_v1(space$display_label) &&
    identical(space$status, "active") && identical(space$created_at_utc, value$created_at_utc)
}

.desktop_product_library_manifest_v1 <- function(library, expected_fingerprint = NULL) {
  path <- file.path(library, ".portelyra-install.json")
  if (!dir.exists(library) || .desktop_product_symlink_v1(library) ||
      !dir.exists(file.path(library, "spotcore")) || !dir.exists(file.path(library, "spotdisplay"))) {
    .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
  }
  value <- .desktop_product_json_read_v1(path, "desktop_product_upgrade_recovery_required")
  if (!.desktop_product_manifest_valid_v1(value, expected_fingerprint)) {
    .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
  }
  source <- file.path(library, ".portelyra-source")
  if (!dir.exists(source) || .desktop_product_symlink_v1(source) || !.desktop_product_owner_mode_v1(source, directory = TRUE)) {
    .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
  }
  source_files <- list.files(source, recursive = TRUE, full.names = TRUE, all.files = TRUE, include.dirs = TRUE, no.. = TRUE)
  if (any(vapply(source_files, .desktop_product_symlink_v1, logical(1L))) || any(vapply(source_files, function(path) {
    !.desktop_product_owner_mode_v1(path, directory = dir.exists(path))
  }, logical(1L)))) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
  actual <- tryCatch(
    .desktop_product_source_fingerprint_v1(source, enforce_current_scope = FALSE),
    error = function(error) NULL
  )
  if (!identical(actual, value$source_fingerprint)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
  value
}

.desktop_product_active_source_v1 <- function(home) {
  home <- .desktop_product_normalize_existing_v1(home)
  paths <- .desktop_product_home_paths_v1(home)
  invisible(.desktop_product_library_manifest_v1(paths$library))
  .desktop_product_normalize_existing_v1(file.path(paths$library, ".portelyra-source"))
}

.desktop_product_upgrade_journal_valid_v1 <- function(value, operation) {
  is.list(value) && identical(names(value), c(
    "contract_version", "operation", "old_source_fingerprint", "new_source_fingerprint",
    "old_product_version", "new_product_version"
  )) && identical(value$contract_version, 1L) && identical(value$operation, operation) &&
    all(vapply(value[c("old_source_fingerprint", "new_source_fingerprint")], function(item) {
      is.character(item) && length(item) == 1L && grepl("^[a-f0-9]{64}$", item)
    }, logical(1))) && all(vapply(value[c("old_product_version", "new_product_version")], function(item) {
      is.character(item) && length(item) == 1L && grepl("^[0-9]+[.][0-9]+[.][0-9]+(-rc[.][0-9]+)?$", item)
    }, logical(1)))
}

.desktop_product_upgrade_receipt_v1 <- function(paths, journal, status, completed_at_utc) {
  .desktop_product_enforce_dir_v1(paths$upgrade_receipts)
  name <- paste0(if (identical(journal$operation, "upgrade")) "upgrade-" else "rollback-", substr(journal$new_source_fingerprint, 1L, 32L), ".json")
  path <- file.path(paths$upgrade_receipts, name)
  value <- list(
    contract_version = 1L, operation = journal$operation, status = status,
    old_source_fingerprint = journal$old_source_fingerprint,
    new_source_fingerprint = journal$new_source_fingerprint,
    old_product_version = journal$old_product_version,
    new_product_version = journal$new_product_version,
    completed_at_utc = completed_at_utc
  )
  if (file.exists(path)) {
    current <- .desktop_product_json_read_v1(path, "desktop_product_upgrade_recovery_required")
    identity_fields <- setdiff(names(value), "completed_at_utc")
    if (!identical(names(current), names(value)) || !identical(current[identity_fields], value[identity_fields]) ||
        !.desktop_product_utc_valid_v1(current$completed_at_utc)) {
      .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    }
  } else .desktop_product_json_write_atomic_v1(path, value)
  invisible(path)
}

# candidate_scope (#571, rc.433): "current" prueft den Kandidaten auch gegen die eingebaute Dateiliste dieses Codes (dev-upgrade aus einem
# Ordner: derselbe Code), "own" nur gegen seine eigene, mitsignierte Liste (update --archive, nach Pruefung von Manifest und Signatur).
.desktop_product_upgrade_impl_v1 <- function(
  project_root, home = desktop_product_default_home_v1(), confirmation, fail_at = "none", candidate_scope = "current"
) {
  .desktop_product_boundary_v1({
    old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
    if (!identical(confirmation, "UPGRADE_LOCAL_RUNTIME")) .desktop_product_abort_v1("desktop_product_upgrade_confirmation_required")
    if (!fail_at %in% c("none", "after_staging", "after_old_moved", "after_new_activated", "after_receipt")) {
      .desktop_product_abort_v1("desktop_product_upgrade_unavailable")
    }
    root <- .desktop_product_project_v1(project_root)
    home <- .desktop_product_normalize_existing_v1(home)
    paths <- .desktop_product_home_paths_v1(home)
    if (!identical(candidate_scope, "current") && !identical(candidate_scope, "own")) .desktop_product_abort_v1("desktop_product_upgrade_unavailable")
    enforce_scope <- identical(candidate_scope, "current")
    candidate_fingerprint <- .desktop_product_source_fingerprint_v1(root, enforce_current_scope = enforce_scope)
    candidate_version <- .desktop_product_version_v1(root)
    session <- file.path(home, "desktop-session.lock")
    session_owner <- .desktop_product_acquire_lock_v1(session, "desktop_product_session_conflict")
    on.exit(if (dir.exists(session)) .desktop_product_release_lock_v1(session, session_owner), add = TRUE)
    install_lock <- file.path(home, "desktop-install.lock")
    install_owner <- .desktop_product_acquire_lock_v1(install_lock, "desktop_product_install_conflict")
    on.exit(if (dir.exists(install_lock)) .desktop_product_release_lock_v1(install_lock, install_owner), add = TRUE)
    recovering <- file.exists(paths$upgrade_journal)
    if (recovering) {
      journal <- .desktop_product_json_read_v1(paths$upgrade_journal, "desktop_product_upgrade_recovery_required")
      if (!.desktop_product_upgrade_journal_valid_v1(journal, "upgrade") ||
          !identical(journal$new_source_fingerprint, candidate_fingerprint) ||
          !identical(journal$new_product_version, candidate_version)) {
        .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
      }
    } else {
      if (!file.exists(paths$install_manifest)) .desktop_product_abort_v1("desktop_product_upgrade_unavailable")
      current <- .desktop_product_library_manifest_v1(paths$library)
      if (identical(current$source_fingerprint, candidate_fingerprint)) {
        return(list(status = "already_current", product_version = candidate_version))
      }
      if (!.desktop_product_version_newer_v1(candidate_version, current$product_version)) {
        .desktop_product_abort_v1("desktop_product_upgrade_unavailable")
      }
      if (dir.exists(paths$upgrade_staging) || file.exists(paths$upgrade_staging) ||
          (file.exists(paths$rollback_library) && !dir.exists(paths$rollback_library)) ||
          (dir.exists(paths$rollback_library) && .desktop_product_symlink_v1(paths$rollback_library))) {
        .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
      }
      if (dir.exists(paths$rollback_library)) invisible(.desktop_product_library_manifest_v1(paths$rollback_library))
      journal <- list(
        contract_version = 1L, operation = "upgrade",
        old_source_fingerprint = current$source_fingerprint, new_source_fingerprint = candidate_fingerprint,
        old_product_version = current$product_version, new_product_version = candidate_version
      )
      .desktop_product_json_write_atomic_v1(paths$upgrade_journal, journal)
    }
    library_manifest <- if (dir.exists(paths$library)) tryCatch(.desktop_product_library_manifest_v1(paths$library), error = function(error) NULL) else NULL
    rollback_manifest <- if (dir.exists(paths$rollback_library)) tryCatch(.desktop_product_library_manifest_v1(paths$rollback_library), error = function(error) NULL) else NULL
    staging_manifest <- if (dir.exists(paths$upgrade_staging)) tryCatch(.desktop_product_library_manifest_v1(paths$upgrade_staging), error = function(error) NULL) else NULL
    if (!is.null(library_manifest) && identical(library_manifest$source_fingerprint, journal$new_source_fingerprint) &&
        !is.null(rollback_manifest) && identical(rollback_manifest$source_fingerprint, journal$old_source_fingerprint)) {
      if (dir.exists(paths$upgrade_staging)) {
        if (.desktop_product_symlink_v1(paths$upgrade_staging)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
        unlink(paths$upgrade_staging, recursive = TRUE, force = TRUE)
      }
    } else {
      if (is.null(staging_manifest) || !identical(staging_manifest$source_fingerprint, journal$new_source_fingerprint)) {
        if (dir.exists(paths$upgrade_staging)) {
          if (.desktop_product_symlink_v1(paths$upgrade_staging)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
          unlink(paths$upgrade_staging, recursive = TRUE, force = TRUE)
        }
        else if (file.exists(paths$upgrade_staging)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
        .desktop_product_install_packages_v1(root, paths$upgrade_staging, enforce_current_scope = enforce_scope)
        .desktop_product_json_write_atomic_v1(
          file.path(paths$upgrade_staging, ".portelyra-install.json"),
          .desktop_product_install_manifest_v1(root, candidate_fingerprint)
        )
      }
      if (identical(fail_at, "after_staging")) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
      if (dir.exists(paths$library)) {
        current <- .desktop_product_library_manifest_v1(paths$library, journal$old_source_fingerprint)
        if (dir.exists(paths$rollback_library)) {
          if (.desktop_product_symlink_v1(paths$rollback_library)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
          unlink(paths$rollback_library, recursive = TRUE, force = TRUE)
        }
        if (file.exists(paths$rollback_library) || !file.rename(paths$library, paths$rollback_library)) {
          .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
        }
      }
      if (identical(fail_at, "after_old_moved")) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
      if (!dir.exists(paths$library)) {
        .desktop_product_library_manifest_v1(paths$rollback_library, journal$old_source_fingerprint)
        .desktop_product_library_manifest_v1(paths$upgrade_staging, journal$new_source_fingerprint)
        if (!file.rename(paths$upgrade_staging, paths$library)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
      }
    }
    invisible(.desktop_product_library_manifest_v1(paths$library, journal$new_source_fingerprint))
    invisible(.desktop_product_library_manifest_v1(paths$rollback_library, journal$old_source_fingerprint))
    if (identical(fail_at, "after_new_activated")) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    completed <- format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    .desktop_product_upgrade_receipt_v1(paths, journal, "completed", completed)
    if (identical(fail_at, "after_receipt")) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    unlink(paths$upgrade_journal, force = TRUE)
    if (file.exists(paths$upgrade_journal)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    list(status = if (recovering) "upgrade_recovered" else "upgraded", product_version = candidate_version)
  }, fallback = "desktop_product_upgrade_unavailable")
}

desktop_product_upgrade_v1 <- function(project_root, home = desktop_product_default_home_v1(), confirmation) {
  .desktop_product_upgrade_impl_v1(project_root, home, confirmation, fail_at = "none")
}

.desktop_product_activity_draft_supersession_barrier_v1 <- function(home) {
  paths <- .desktop_product_home_paths_v1(home)
  if (!file.exists(paths$registry) || dir.exists(paths$registry)) return(FALSE)
  registry <- .desktop_product_json_read_v1(paths$registry, "desktop_product_rollback_incompatible")
  if (!.desktop_product_registry_valid_v1(registry)) .desktop_product_abort_v1("desktop_product_rollback_incompatible")
  barrier <- file.path(
    paths$data_root, registry$tenant_id, registry$user_id,
    registry$active_data_space_id, "activity-drafts-v1", ".writer.lock"
  )
  if (!file.exists(barrier) && !dir.exists(barrier)) return(FALSE)
  if (!dir.exists(barrier) || .desktop_product_symlink_v1(barrier) ||
      !.desktop_product_owner_mode_v1(barrier, directory = TRUE)) {
    .desktop_product_abort_v1("desktop_product_rollback_incompatible")
  }
  children <- list.files(barrier, all.files = TRUE, no.. = TRUE, full.names = TRUE)
  marker <- file.path(barrier, "immutable-source-supersession-v1.json")
  mixed_marker <- file.path(barrier, "mixed-source-retirement-v1.json")
  expected_children <- c(marker, if (file.exists(mixed_marker)) mixed_marker else character())
  if (!identical(sort(children, method = "radix"), sort(expected_children, method = "radix")) ||
      !file.exists(marker) || dir.exists(marker) || .desktop_product_symlink_v1(marker) ||
      !.desktop_product_owner_mode_v1(marker)) {
    .desktop_product_abort_v1("desktop_product_rollback_incompatible")
  }
  value <- .desktop_product_json_read_v1(marker, "desktop_product_rollback_incompatible")
  barrier_material <- list(
    activity_draft_writer_barrier_version = 1L,
    legacy_writer_blocked = TRUE,
    minimum_writer_capability = "immutable_exact_source_generation_supersession_v1"
  )
  expected_fingerprint <- digest::digest(charToRaw(enc2utf8(as.character(jsonlite::toJSON(
    barrier_material, auto_unbox = TRUE, null = "null", na = "null", digits = NA, pretty = FALSE
  )))), algo = "sha256", serialize = FALSE)
  if (!is.list(value) || !setequal(names(value), c(
    "activity_draft_writer_barrier_version", "minimum_writer_capability",
    "legacy_writer_blocked", "barrier_fingerprint"
  )) || !identical(value$activity_draft_writer_barrier_version, 1L) ||
      !identical(value$minimum_writer_capability, "immutable_exact_source_generation_supersession_v1") ||
      !isTRUE(value$legacy_writer_blocked) || !is.character(value$barrier_fingerprint) ||
      length(value$barrier_fingerprint) != 1L || !identical(value$barrier_fingerprint, expected_fingerprint)) {
    .desktop_product_abort_v1("desktop_product_rollback_incompatible")
  }
  if (file.exists(mixed_marker)) {
    if (dir.exists(mixed_marker) || .desktop_product_symlink_v1(mixed_marker) ||
        !.desktop_product_owner_mode_v1(mixed_marker)) {
      .desktop_product_abort_v1("desktop_product_rollback_incompatible")
    }
    mixed_value <- .desktop_product_json_read_v1(mixed_marker, "desktop_product_rollback_incompatible")
    mixed_material <- list(
      activity_draft_writer_barrier_version = 2L,
      legacy_writer_blocked = TRUE,
      minimum_writer_capability = "mixed_source_retirement_preserve_committed_v1"
    )
    mixed_fingerprint <- digest::digest(charToRaw(enc2utf8(as.character(jsonlite::toJSON(
      mixed_material, auto_unbox = TRUE, null = "null", na = "null", digits = NA, pretty = FALSE
    )))), algo = "sha256", serialize = FALSE)
    if (!is.list(mixed_value) || !setequal(names(mixed_value), c(
      "activity_draft_writer_barrier_version", "minimum_writer_capability",
      "legacy_writer_blocked", "barrier_fingerprint"
    )) || !identical(mixed_value$activity_draft_writer_barrier_version, 2L) ||
        !identical(mixed_value$minimum_writer_capability, "mixed_source_retirement_preserve_committed_v1") ||
        !isTRUE(mixed_value$legacy_writer_blocked) || !is.character(mixed_value$barrier_fingerprint) ||
        length(mixed_value$barrier_fingerprint) != 1L ||
        !identical(mixed_value$barrier_fingerprint, mixed_fingerprint)) {
      .desktop_product_abort_v1("desktop_product_rollback_incompatible")
    }
  }
  TRUE
}

.desktop_product_activity_draft_mixed_source_retirement_barrier_v1 <- function(home) {
  if (!.desktop_product_activity_draft_supersession_barrier_v1(home)) return(FALSE)
  paths <- .desktop_product_home_paths_v1(home)
  registry <- .desktop_product_json_read_v1(paths$registry, "desktop_product_rollback_incompatible")
  marker <- file.path(
    paths$data_root, registry$tenant_id, registry$user_id,
    registry$active_data_space_id, "activity-drafts-v1", ".writer.lock",
    "mixed-source-retirement-v1.json"
  )
  file.exists(marker) && !dir.exists(marker)
}

.desktop_product_library_supports_draft_supersession_v1 <- function(library) {
  source <- file.path(library, ".portelyra-source")
  registry_path <- file.path(source, "contracts", "desktop-product", "v1", "source-fingerprints.csv")
  rows <- tryCatch(read.csv(registry_path, stringsAsFactors = FALSE), error = function(error) NULL)
  required <- c(
    "docs/decisions/ADR-144-immutable-activity-draft-source-generation-supersession.md",
    "contracts/desktop-product-activity-draft/v1/source-supersession-generation.schema.json",
    "contracts/desktop-product-activity-draft/v1/source-supersession-writer-barrier.schema.json"
  )
  !is.null(rows) && identical(names(rows), c("path", "sha256")) && all(required %in% rows$path)
}

.desktop_product_library_supports_draft_mixed_source_retirement_v1 <- function(library) {
  source <- file.path(library, ".portelyra-source")
  registry_path <- file.path(source, "contracts", "desktop-product", "v1", "source-fingerprints.csv")
  rows <- tryCatch(read.csv(registry_path, stringsAsFactors = FALSE), error = function(error) NULL)
  required <- c(
    "docs/decisions/ADR-145-mixed-state-activity-draft-source-retirement.md",
    "contracts/desktop-product-activity-draft/v1/mixed-source-retirement-trusted-preview.schema.json",
    "contracts/desktop-product-activity-draft/v1/mixed-source-retirement-writer-barrier.schema.json"
  )
  !is.null(rows) && identical(names(rows), c("path", "sha256")) && all(required %in% rows$path)
}

.desktop_product_rollback_target_supports_draft_supersession_v1 <- function(paths, target_fingerprint) {
  candidates <- c(paths$library, paths$rollback_library, paths$rollback_staging)
  any(vapply(candidates, function(candidate) {
    manifest <- if (dir.exists(candidate)) tryCatch(.desktop_product_library_manifest_v1(candidate), error = function(error) NULL) else NULL
    !is.null(manifest) && identical(manifest$source_fingerprint, target_fingerprint) &&
      .desktop_product_library_supports_draft_supersession_v1(candidate)
  }, logical(1L)))
}

.desktop_product_rollback_target_supports_draft_mixed_source_retirement_v1 <- function(paths, target_fingerprint) {
  candidates <- c(paths$library, paths$rollback_library, paths$rollback_staging)
  any(vapply(candidates, function(candidate) {
    manifest <- if (dir.exists(candidate)) tryCatch(.desktop_product_library_manifest_v1(candidate), error = function(error) NULL) else NULL
    !is.null(manifest) && identical(manifest$source_fingerprint, target_fingerprint) &&
      .desktop_product_library_supports_draft_mixed_source_retirement_v1(candidate)
  }, logical(1L)))
}

.desktop_product_selected_fetch_required_v1 <- function(home, area_name = "market-fx-batch-execution-v1", marker_name = ".selected-fetch-authority-v1.json") {
  paths <- .desktop_product_home_paths_v1(home)
  if (!file.exists(paths$registry) && !.desktop_product_symlink_v1(paths$registry)) return(FALSE)
  registry <- .desktop_product_json_read_v1(paths$registry, "desktop_product_rollback_incompatible")
  if (!.desktop_product_registry_valid_v1(registry)) .desktop_product_abort_v1("desktop_product_rollback_incompatible")
  tenant <- file.path(paths$data_root, registry$tenant_id)
  user <- file.path(tenant, registry$user_id)
  space <- file.path(user, registry$active_data_space_id)
  area <- file.path(space, area_name)
  chain <- c(paths$data_root, tenant, user, space, area)
  if (any(vapply(chain, .desktop_product_symlink_v1, logical(1L))))
    .desktop_product_abort_v1("desktop_product_rollback_incompatible")
  marker <- file.path(area, marker_name)
  if (!file.exists(marker) && !dir.exists(marker) && !.desktop_product_symlink_v1(marker)) return(FALSE)
  # Existence is a conservative capability requirement; never edit/read Domain facts.
  info <- file.info(c(chain, marker))
  if (.desktop_product_symlink_v1(marker) || anyNA(info$mode) || anyNA(info$uname) ||
      any(bitwAnd(as.integer(info$mode), 511L) != c(rep(448L,length(chain)),384L)) ||
      any(info$uname != Sys.info()[["effective_user"]]) || dir.exists(marker))
    .desktop_product_abort_v1("desktop_product_rollback_incompatible")
  TRUE
}

.desktop_product_library_supports_selected_fetch_v1 <- function(library, required_path = "docs/decisions/ADR-206-selected-pending-batch-fetch-authority.md") {
  registry <- file.path(library, ".portelyra-source", "contracts", "desktop-product", "v1", "source-fingerprints.csv")
  rows <- tryCatch(read.csv(registry, stringsAsFactors=FALSE), error=function(error) NULL)
  !is.null(rows) && identical(names(rows), c("path","sha256")) &&
    required_path %in% rows$path
}

.desktop_product_rollback_target_supports_selected_fetch_v1 <- function(paths, fingerprint, required_path = "docs/decisions/ADR-206-selected-pending-batch-fetch-authority.md") {
  any(vapply(c(paths$library, paths$rollback_library, paths$rollback_staging), function(candidate) {
    manifest <- if (dir.exists(candidate)) tryCatch(.desktop_product_library_manifest_v1(candidate), error=function(error) NULL) else NULL
    !is.null(manifest) && identical(manifest$source_fingerprint, fingerprint) &&
      .desktop_product_library_supports_selected_fetch_v1(candidate, required_path)
  }, logical(1L)))
}

.desktop_product_rollback_impl_v1 <- function(
  project_root, home = desktop_product_default_home_v1(), confirmation, fail_at = "none"
) {
  .desktop_product_boundary_v1({
    old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
    if (!identical(confirmation, "ROLLBACK_LOCAL_RUNTIME")) .desktop_product_abort_v1("desktop_product_rollback_confirmation_required")
    if (!fail_at %in% c("none", "after_current_moved", "after_old_activated", "after_receipt")) {
      .desktop_product_abort_v1("desktop_product_rollback_unavailable")
    }
    root <- .desktop_product_project_v1(project_root); home <- .desktop_product_normalize_existing_v1(home)
    paths <- .desktop_product_home_paths_v1(home)
    session <- file.path(home, "desktop-session.lock")
    session_owner <- .desktop_product_acquire_lock_v1(session, "desktop_product_session_conflict")
    on.exit(if (dir.exists(session)) .desktop_product_release_lock_v1(session, session_owner), add = TRUE)
    install_lock <- file.path(home, "desktop-install.lock")
    install_owner <- .desktop_product_acquire_lock_v1(install_lock, "desktop_product_install_conflict")
    on.exit(if (dir.exists(install_lock)) .desktop_product_release_lock_v1(install_lock, install_owner), add = TRUE)
    recovering <- file.exists(paths$upgrade_journal)
    if (recovering) {
      journal <- .desktop_product_json_read_v1(paths$upgrade_journal, "desktop_product_upgrade_recovery_required")
      if (!.desktop_product_upgrade_journal_valid_v1(journal, "rollback")) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    } else {
      if (!dir.exists(paths$library) || !dir.exists(paths$rollback_library) || dir.exists(paths$rollback_staging) || file.exists(paths$rollback_staging)) {
        .desktop_product_abort_v1("desktop_product_rollback_unavailable")
      }
      current <- .desktop_product_library_manifest_v1(paths$library)
      previous <- .desktop_product_library_manifest_v1(paths$rollback_library)
      if (.desktop_product_selected_fetch_required_v1(home, "desktop-fx-history-review-v1", ".attempt-v2.lock") &&
          !.desktop_product_library_supports_selected_fetch_v1(paths$rollback_library, "migrations/reference/desktop_fx_history_attempt_v2.py"))
        .desktop_product_abort_v1("desktop_product_rollback_incompatible")
      if (.desktop_product_selected_fetch_required_v1(home) &&
          !.desktop_product_library_supports_selected_fetch_v1(paths$rollback_library))
        .desktop_product_abort_v1("desktop_product_rollback_incompatible")
      if (.desktop_product_activity_draft_supersession_barrier_v1(home) &&
          !.desktop_product_library_supports_draft_supersession_v1(paths$rollback_library)) {
        .desktop_product_abort_v1("desktop_product_rollback_incompatible")
      }
      if (.desktop_product_activity_draft_mixed_source_retirement_barrier_v1(home) &&
          !.desktop_product_library_supports_draft_mixed_source_retirement_v1(paths$rollback_library)) {
        .desktop_product_abort_v1("desktop_product_rollback_incompatible")
      }
      journal <- list(
        contract_version = 1L, operation = "rollback",
        old_source_fingerprint = current$source_fingerprint, new_source_fingerprint = previous$source_fingerprint,
        old_product_version = current$product_version, new_product_version = previous$product_version
      )
      .desktop_product_json_write_atomic_v1(paths$upgrade_journal, journal)
    }
    if (.desktop_product_selected_fetch_required_v1(home, "desktop-fx-history-review-v1", ".attempt-v2.lock") &&
        !.desktop_product_rollback_target_supports_selected_fetch_v1(paths, journal$new_source_fingerprint, "migrations/reference/desktop_fx_history_attempt_v2.py"))
      .desktop_product_abort_v1("desktop_product_rollback_incompatible")
    if (.desktop_product_selected_fetch_required_v1(home) &&
        !.desktop_product_rollback_target_supports_selected_fetch_v1(paths, journal$new_source_fingerprint))
      .desktop_product_abort_v1("desktop_product_rollback_incompatible")
    if (.desktop_product_activity_draft_supersession_barrier_v1(home) &&
        !.desktop_product_rollback_target_supports_draft_supersession_v1(paths, journal$new_source_fingerprint)) {
      .desktop_product_abort_v1("desktop_product_rollback_incompatible")
    }
    if (.desktop_product_activity_draft_mixed_source_retirement_barrier_v1(home) &&
        !.desktop_product_rollback_target_supports_draft_mixed_source_retirement_v1(paths, journal$new_source_fingerprint)) {
      .desktop_product_abort_v1("desktop_product_rollback_incompatible")
    }
    library_manifest <- if (dir.exists(paths$library)) tryCatch(.desktop_product_library_manifest_v1(paths$library), error = function(error) NULL) else NULL
    backup_manifest <- if (dir.exists(paths$rollback_library)) tryCatch(.desktop_product_library_manifest_v1(paths$rollback_library), error = function(error) NULL) else NULL
    forward_manifest <- if (dir.exists(paths$rollback_staging)) tryCatch(.desktop_product_library_manifest_v1(paths$rollback_staging), error = function(error) NULL) else NULL
    if (!is.null(library_manifest) && identical(library_manifest$source_fingerprint, journal$old_source_fingerprint)) {
      if (!is.null(forward_manifest) || !file.rename(paths$library, paths$rollback_staging)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
      forward_manifest <- .desktop_product_library_manifest_v1(paths$rollback_staging, journal$old_source_fingerprint)
      library_manifest <- NULL
    }
    if (identical(fail_at, "after_current_moved")) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    if (is.null(library_manifest)) {
      if (is.null(backup_manifest) || !identical(backup_manifest$source_fingerprint, journal$new_source_fingerprint) ||
          !file.rename(paths$rollback_library, paths$library)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
      library_manifest <- .desktop_product_library_manifest_v1(paths$library, journal$new_source_fingerprint)
      backup_manifest <- NULL
    }
    if (identical(fail_at, "after_old_activated")) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    if (!dir.exists(paths$rollback_library)) {
      if (is.null(forward_manifest)) forward_manifest <- .desktop_product_library_manifest_v1(paths$rollback_staging, journal$old_source_fingerprint)
      if (!file.rename(paths$rollback_staging, paths$rollback_library)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    }
    invisible(.desktop_product_library_manifest_v1(paths$library, journal$new_source_fingerprint))
    invisible(.desktop_product_library_manifest_v1(paths$rollback_library, journal$old_source_fingerprint))
    completed <- format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    .desktop_product_upgrade_receipt_v1(paths, journal, "completed", completed)
    if (identical(fail_at, "after_receipt")) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    unlink(paths$upgrade_journal, force = TRUE)
    if (file.exists(paths$upgrade_journal)) .desktop_product_abort_v1("desktop_product_upgrade_recovery_required")
    list(status = if (recovering) "rollback_recovered" else "rolled_back", product_version = journal$new_product_version)
  }, fallback = "desktop_product_rollback_unavailable")
}

desktop_product_rollback_v1 <- function(project_root, home = desktop_product_default_home_v1(), confirmation) {
  .desktop_product_rollback_impl_v1(project_root, home, confirmation, fail_at = "none")
}

desktop_product_runtime_initialize_v1 <- function(
  home = desktop_product_default_home_v1(), data_space_label, created_at_utc, confirmation
) {
  .desktop_product_boundary_v1({
    old_umask <- Sys.umask("0077")
    on.exit(Sys.umask(old_umask), add = TRUE)
    if (!identical(confirmation, "INITIALIZE_LOCAL_DESKTOP")) {
      .desktop_product_abort_v1("desktop_product_registry_confirmation_required")
    }
    if (!.desktop_product_label_valid_v1(data_space_label) || !.desktop_product_utc_valid_v1(created_at_utc)) {
      .desktop_product_abort_v1("desktop_product_registry_invalid")
    }
    home <- .desktop_product_ensure_home_v1(home)
    paths <- .desktop_product_home_paths_v1(home)
    lock <- file.path(home, "desktop-runtime.lock")
    lock_owner <- .desktop_product_acquire_lock_v1(lock, "desktop_product_registry_conflict")
    on.exit(if (dir.exists(lock)) .desktop_product_release_lock_v1(lock, lock_owner), add = TRUE)
    if (file.exists(paths$registry)) {
      current <- .desktop_product_json_read_v1(paths$registry)
      if (!.desktop_product_registry_valid_v1(current) || !identical(current$data_spaces[[1L]]$display_label, data_space_label)) {
        .desktop_product_abort_v1("desktop_product_registry_conflict")
      }
      return(list(status = "already_initialized", runtime_mode = "desktop_product", data_space_label = data_space_label))
    }
    .desktop_product_enforce_dir_v1(paths$data_root)
    registry <- list(
      contract_version = 1L,
      runtime_mode = "desktop_product",
      registry_revision = 1L,
      tenant_id = .desktop_product_random_id_v1("ten_"),
      user_id = .desktop_product_random_id_v1("usr_"),
      active_data_space_id = .desktop_product_random_id_v1("sbx_"),
      data_spaces = list(list(
        data_space_id = NULL, display_label = data_space_label, status = "active", created_at_utc = created_at_utc
      )),
      created_at_utc = created_at_utc
    )
    registry$data_spaces[[1L]]$data_space_id <- registry$active_data_space_id
    .desktop_product_json_write_atomic_v1(paths$registry, registry)
    list(status = "initialized", runtime_mode = "desktop_product", data_space_label = data_space_label)
  })
}

desktop_product_runtime_load_v1 <- function(home = desktop_product_default_home_v1()) {
  .desktop_product_boundary_v1({
    home <- .desktop_product_normalize_existing_v1(home)
    if (!.desktop_product_owner_mode_v1(home, directory = TRUE)) .desktop_product_abort_v1("desktop_product_permissions_invalid")
    paths <- .desktop_product_home_paths_v1(home)
    registry <- .desktop_product_json_read_v1(paths$registry, "desktop_product_not_initialized")
    if (!.desktop_product_registry_valid_v1(registry)) .desktop_product_abort_v1("desktop_product_registry_invalid")
    # Gesperrt (#535): nie still einen anderen Ort lesen.
    if (isTRUE(paths$locked)) .desktop_product_abort_v1("desktop_product_locked")
    data_root <- .desktop_product_normalize_existing_v1(paths$data_root)
    if (!.desktop_product_owner_mode_v1(data_root, directory = TRUE)) .desktop_product_abort_v1("desktop_product_permissions_invalid")
    context <- new_desktop_product_runtime_v1(
      data_root, registry$tenant_id, registry$user_id, registry$active_data_space_id
    )
    structure(
      list(
        contract_version = 1L,
        runtime_mode = "desktop_product",
        context = context,
        data_space_label = registry$data_spaces[[1L]]$display_label,
        registry_revision = 1L,
        home = home,
        library = paths$library
      ),
      class = "spot_desktop_product_runtime_v1"
    )
  })
}

desktop_product_runtime_valid_v1 <- function(runtime) {
  inherits(runtime, "spot_desktop_product_runtime_v1") && is.list(runtime) &&
    identical(names(runtime), c(
      "contract_version", "runtime_mode", "context", "data_space_label", "registry_revision", "home", "library"
    )) && identical(runtime$contract_version, 1L) && identical(runtime$runtime_mode, "desktop_product") &&
    identical(runtime$registry_revision, 1L) && .desktop_product_label_valid_v1(runtime$data_space_label) &&
    runtime_context_valid(runtime$context) && identical(runtime$context$runtime_mode, "desktop_product") &&
    identical(runtime$context$role, "desktop_owner") && dir.exists(runtime$home)
}

desktop_product_initialize_data_space_v1 <- function(runtime, contract_root, created_at_utc, confirmation) {
  .desktop_product_boundary_v1({
    old_umask <- Sys.umask("0077")
    on.exit(Sys.umask(old_umask), add = TRUE)
    if (!identical(confirmation, "INITIALIZE_EMPTY_DATA_SPACE")) {
      .desktop_product_abort_v1("desktop_product_data_space_confirmation_required")
    }
    if (!desktop_product_runtime_valid_v1(runtime)) .desktop_product_abort_v1("desktop_product_context_invalid")
    canonical_repository_bootstrap_v1(runtime$context, contract_root, created_at_utc)
  }, fallback = "desktop_product_workspace_invalid")
}

desktop_product_workspace_v1 <- function(runtime) {
  .desktop_product_boundary_v1({
    if (!desktop_product_runtime_valid_v1(runtime)) .desktop_product_abort_v1("desktop_product_context_invalid")
    if (!file.exists(runtime_canonical_path(runtime$context))) {
      return(list(
        contract_version = 1L, status = "uninitialized", data_space_label = runtime$data_space_label,
        counts = list(portfolio_count = 0L, account_count = 0L, asset_count = 0L, transaction_count = 0L),
        portfolios = list(), accounts = list(), assets = list(), transactions = list()
      ))
    }
    catalog <- catalog_read_v1(runtime$context)
    portfolios <- lapply(catalog$portfolios, function(row) list(
      name = row$display_name, currency = row$base_currency, status = row$status
    ))
    accounts <- lapply(catalog$accounts, function(row) list(
      name = row$display_name, type = row$account_type, status = row$status
    ))
    assets <- lapply(catalog$assets, function(row) list(
      name = row$display_name, type = row$asset_type, currency = row$price_currency, status = row$status
    ))
    transactions <- list()
    for (portfolio in catalog$portfolios) {
      history <- transaction_read_history_v1(runtime$context, portfolio$portfolio_id)
      for (entry in history$entries) if (isTRUE(entry$is_current)) {
        transactions[[length(transactions) + 1L]] <- list(
          date = entry$record$local_date, type = entry$record$transaction_type,
          state = if (identical(entry$record$record_action, "void")) "void" else "current"
        )
      }
    }
    list(
      contract_version = 1L,
      status = if (length(portfolios) + length(accounts) + length(assets) + length(transactions)) "ready" else "empty",
      data_space_label = runtime$data_space_label,
      counts = list(
        portfolio_count = as.integer(length(portfolios)), account_count = as.integer(length(accounts)),
        asset_count = as.integer(length(assets)), transaction_count = as.integer(length(transactions))
      ),
      portfolios = portfolios, accounts = accounts, assets = assets, transactions = transactions
    )
  })
}

desktop_product_safe_error_code_v1 <- function(error) {
  code <- tryCatch(error$code, error = function(condition) NULL)
  if (is.character(code) && length(code) == 1L &&
      (startsWith(code, "desktop_product_") || startsWith(code, "desktop_onboarding_") ||
       startsWith(code, "desktop_run_center_") || startsWith(code, "desktop_release_") ||
       startsWith(code, "desktop_catalog_") || startsWith(code, "desktop_csv_") || startsWith(code, "data_transaction_editor_") ||
       startsWith(code, "data_asset_activity_editor_") || startsWith(code, "desktop_asset_activity_") ||
       startsWith(code, "data_cash_coverage_editor_") || startsWith(code, "desktop_cash_coverage_") ||
       startsWith(code, "data_provider_mapping_") || startsWith(code, "provider_mapping_") ||
       startsWith(code, "data_provider_search_") || startsWith(code, "desktop_provider_search_") ||
       startsWith(code, "data_provider_probe_") || startsWith(code, "desktop_provider_probe_") ||
       startsWith(code, "data_provider_promotion_") || startsWith(code, "desktop_provider_promotion_") ||
       startsWith(code, "data_market_history_plan_") || startsWith(code, "desktop_market_history_plan_") ||
       startsWith(code, "data_market_history_fetch_") || startsWith(code, "desktop_market_history_fetch_") ||
       startsWith(code, "data_market_history_review_") || startsWith(code, "desktop_market_history_review_") ||
       startsWith(code, "data_market_history_coverage_") || startsWith(code, "desktop_market_history_coverage_") ||
       startsWith(code, "data_market_valuation_") || startsWith(code, "desktop_market_valuation_") ||
       startsWith(code, "manual_price_") || startsWith(code, "data_manual_price_") ||
       startsWith(code, "asset_center_") ||
       startsWith(code, "market_history_carry_") ||
       startsWith(code, "data_market_history_carry_") ||
       startsWith(code, "desktop_market_history_carry_") ||
       startsWith(code, "data_fx_demand_coverage_") || startsWith(code, "desktop_fx_demand_coverage_") ||
       startsWith(code, "data_fx_pair_probe_") || startsWith(code, "desktop_fx_pair_probe_") ||
       startsWith(code, "data_fx_pair_promotion_") || startsWith(code, "desktop_fx_pair_promotion_") ||
       startsWith(code, "data_fx_history_review_") || startsWith(code, "desktop_fx_history_review_") ||
       startsWith(code, "data_market_calendar_gap_") || startsWith(code, "desktop_market_calendar_gap_") ||
       startsWith(code, "desktop_calendar_gap_review_") || startsWith(code, "market_calendar_registry_") || startsWith(code, "market_calendar_correction_") ||
       startsWith(code, "desktop_reward_daily_close_") || startsWith(code, "reward_valuation_") || startsWith(code, "data_reward_daily_close_") ||
       startsWith(code, "data_portfolio_csv_exchange_") || startsWith(code, "portfolio_csv_") ||
       startsWith(code, "tax_ui_") || startsWith(code, "transaction_command_") || startsWith(code, "canonical_repository_"))) return(code)
  "desktop_product_boundary_failed"
}
