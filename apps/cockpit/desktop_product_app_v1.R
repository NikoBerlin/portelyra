project_root <- getOption("portelyra.desktop.project_root")
runtime <- getOption("portelyra.desktop.runtime")
if (!is.character(project_root) || !is.list(runtime) || !is.list(runtime$context)) stop("desktop_product_app_context_invalid", call. = FALSE)
source(file.path(project_root, "apps", "shared", "portelyra_ui_shell.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_activity_v1.R"), local = TRUE)
# Rundgang im Demo (#578): nur mit der Option portelyra.desktop.demo eingebunden.
source(file.path(project_root, "apps", "shared", "desktop_tour_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_help_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_program_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_workflow_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_workflow_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "display_new_state_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_portfolio_snapshot_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "data_stands_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "data_tax_settings_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "cockpit", "datenbasis_v1.R"), local = TRUE)
# Das Cockpit zeigt die Datenbasis (rc.313, #478; von rc.313 bis rc.417 hiess die App „Datenbasis“, seit rc.418 wieder „Cockpit“, #490). Festlegung 20.10.2026: Grundlagen statt Ergebnisse - Daten, Herkunft und
# Konfiguration, keine Werte und keine GuV. Festlegung 24.10.2026: Stichtag und Momentaufnahme stehen jetzt in der Analyse,
# veroeffentlicht wird in der Data-App. Die App liest nur Veroeffentlichtes mit der Rolle "viewer". Seit rc.314 dazu die eigene
# Veroeffentlichung der Datenbasis (Buchungen je Konto, Assets und Kurse, Wechselkurse, Belege, Einstellungen).
snapshot_reader <- tryCatch(spotdisplay::new_desktop_product_display_context_v1(
  runtime$context$data_root, "viewer", runtime$context$tenant_id,
  runtime$context$user_id, runtime$context$data_space_id), error = function(error) NULL)
service <- new_desktop_workflow_service_v1(project_root, runtime, "viewer")
ui <- portelyra_app_shell(
  "cockpit", "Portelyra Cockpit", "Worauf Analyse und Steuer rechnen: Buchungen, Bestände, Kurse, Belege und Einstellungen – und wie weit jede Datenart reicht. Werte und GuV stehen in der Analyse.",
  capabilities = c("Nur veröffentlichte Stände", "Herkunft und Stand der Daten", "Einstellungen der Rechnung"),
  actions = shiny::actionButton("refresh", "Neu lesen", class = "btn-default"),
  # Aktualisierung, „Läuft gerade“ und Einstellungen links (#540): aus dem veroeffentlichten Stand, die Knoepfe fuehren nach Data.
  sidebar_activity = desktop_activity_sidebar_ui_v1(help_app = "cockpit", version = desktop_program_version_v1(project_root)),
  shiny::uiOutput("new_state"),
  datenbasis_ui_v1())
server <- function(input, output, session) {
  desktop_activity_server_v1(input, output, session, desktop_activity_reader_v1(project_root, runtime$context, "viewer"))
  desktop_help_server_v1(input, output, session, project_root, "cockpit")
  # Neuere Version gefunden (#562 Paket 3): nur update-status.json lesen, nie ins Netz; der Link fuehrt zum Reiter „Programm“ in Data.
  desktop_program_server_v1(input, output, session, runtime$home, desktop_program_version_v1(project_root),
                            desktop_activity_data_link_v1("program", "Ansehen", "pl-activity-link"))
  workflow <- shiny::reactiveVal(desktop_workflow_display_state_v1())
  snapshot <- shiny::reactiveVal(NULL)
  basis <- shiny::reactiveVal(NULL)
  small_limit <- shiny::reactiveVal("1")
  # Umfang je Portfolio (#542): aus denselben Anzeige-Einstellungen, nur wenn veroeffentlicht - sonst NULL und alles wie bisher.
  scope <- shiny::reactiveVal(NULL)
  load_all <- function() {
    display <- if (is.null(snapshot_reader)) NULL else tryCatch(spotdisplay::read_display_settings_latest_v1(snapshot_reader, project_root),
                                                                 error = function(error) NULL)
    small_limit(if (is.list(display) && is.character(display$small_holdings_threshold)) display$small_holdings_threshold else "1")
    scope(desktop_scope_of_v1(display))
    workflow(tryCatch(desktop_workflow_display_state_v1(desktop_workflow_read_latest_v1(service)),
      spot_display_reader_error = function(error) desktop_workflow_display_state_v1(error_code = error$code),
      error = function(error) desktop_workflow_display_state_v1(error_code = "display_boundary_failed")))
    snapshot(if (is.null(snapshot_reader)) NULL else tryCatch(spotdisplay::read_portfolio_snapshot_latest_v5(snapshot_reader, project_root),
                                                             error = function(error) NULL))
    basis(if (is.null(snapshot_reader)) list(value = NULL, code = "display_context_invalid") else tryCatch(
      list(value = spotdisplay::read_data_basis_latest_v1(snapshot_reader, project_root), code = NULL),
      spot_display_reader_error = function(error) list(value = NULL, code = error$code),
      error = function(error) list(value = NULL, code = "display_boundary_failed")))
  }
  load_all(); shiny::observeEvent(input$refresh, load_all(), ignoreInit = TRUE)
  # Neuer Stand veroeffentlicht (#457): Hinweis mit "Neu lesen", sobald sich ein gelesener Bereich seit dem Laden geaendert hat.
  fresh <- display_new_state_server_v1(output, session, "new_state", function() display_new_state_marker_v1(service$context, c("desktop_workflow", "portfolio_snapshot", "data_basis")),
                                       button = "„Neu lesen“ oben rechts")
  fresh$mark(); shiny::observeEvent(input$refresh, fresh$mark(), ignoreInit = TRUE)
  datenbasis_server_v1(input, output, session, snapshot, workflow, basis, threshold = small_limit, scope = scope)
  desktop_activity_scope_server_v1(output, scope)
}
shiny::shinyApp(ui, server)
