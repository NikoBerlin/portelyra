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
source(file.path(project_root, "apps", "shared", "desktop_portfolio_snapshot_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_intraday_snapshot_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "data_portfolio_snapshot_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "analysis", "analysis_history_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "analysis", "analysis_assets_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "analysis", "analysis_projection_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "analysis", "analysis_compare_v1.R"), local = TRUE)
# Punkt „jetzt“ in allen Bildern (#512): die Momentaufnahme je Asset.
source(file.path(project_root, "apps", "analysis", "analysis_moment_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "analysis", "analysis_snapshots_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "display_new_state_v1.R"), local = TRUE)
service <- new_desktop_workflow_service_v1(project_root, runtime, "analysis_viewer")
# Die veroeffentlichte Tageshistorie (#473) liest dieselbe Rolle; die Analyse zeichnet sie nur.
history_read <- function() spotdisplay::read_portfolio_history_latest_v1(service$context, project_root)
# Die Tagesreihen je Asset, Klasse und Gruppe erst bei Bedarf (#503), gebunden an den Verweis im geprueften Kern.
history_part <- function(part) spotdisplay::read_portfolio_history_part_v1(service$context, part)
# Anzeige-Einstellungen (#500) und Zeiger der gelesenen Bereiche (#457).
history_display <- function() spotdisplay::read_display_settings_latest_v1(service$context, project_root)
history_marker <- function() display_new_state_marker_v1(service$context, c("portfolio_history", "desktop_workflow", "display_settings"))
# Stichtag und Momentaufnahme (rc.313, #478): nur der lesende Teil des Snapshot-Dienstes - veroeffentlicht wird in der Data-App.
snapshot_reader <- data_portfolio_snapshot_reader_v1(tryCatch(new_data_portfolio_snapshot_service_v1(project_root, runtime$context),
                                                              error = function(error) NULL))
ui <- portelyra_app_shell(
  "analysis", "Portelyra Analyse", "Ergebnisse aus der veröffentlichten Tageshistorie, den Stichtags-Snapshots, der Momentaufnahme und dem letzten Abschluss. Gerechnet wird beim Veröffentlichen; hier wird nur gezeigt.",
  capabilities = c("Nur veröffentlichte Stände", "Brutto und netto (Projektion)", "Tagesgenaue Historie"),
  actions = shiny::actionButton("refresh", "Neu lesen", class = "btn-default"),
  # Aktualisierung, „Läuft gerade“ und Einstellungen links (#540): aus dem veroeffentlichten Stand, die Knoepfe fuehren nach Data.
  sidebar_activity = desktop_activity_sidebar_ui_v1(help_app = "analysis", version = desktop_program_version_v1(project_root)),
  # Reiter wie in der Data-App (#485): kein Scrollen über alle Bereiche.
  shiny::tags$style(shiny::HTML(ANALYSIS_HISTORY_TINT_STYLE_V1)),
  shiny::uiOutput("analysis_new_state"),
  # Umfang je Portfolio (#542): eine Statusflaeche, nur wenn ein Baustein abgeschaltet ist, den die Analyse zeigt.
  shiny::uiOutput("analysis_scope_state", class = "pl-scope-slot"),
  # Ein Zeitraum fuer alle Reiter mit Zeitachse (#531 Punkt 1), ueber den Reitern.
  analysis_history_central_period_ui_v1(),
  shiny::div(class = "pl-workspace-tabs", shiny::tabsetPanel(id = "analysis_tab",
    shiny::tabPanel("Verlauf", value = "verlauf", analysis_history_verlauf_ui_v1()),
    shiny::tabPanel("Rendite", value = "rendite", analysis_history_rendite_ui_v1()),
    shiny::tabPanel("Vergleich", value = "vergleich", analysis_compare_ui_v1()),
    shiny::tabPanel("Assets und Gruppen", value = "assets", analysis_assets_ui_v1()),
    shiny::tabPanel("Projektion", value = "projektion", analysis_projection_ui_v1()),
    shiny::tabPanel("Stichtag", value = "stichtag", analysis_stichtag_ui_v1()),
    shiny::tabPanel("Momentaufnahme", value = "moment", analysis_moment_ui_v1()),
    shiny::tabPanel("Abschluss", value = "abschluss",
      shiny::p(class = "pl-section-copy", "Die Ergebnisse des letzten abgeschlossenen Laufs (in der App „Daten“ mit „Alles aktualisieren“). Cockpit, Steuer und Analyse zeigen denselben Lauf."),
      portelyra_card("Geltender Abschluss", help = "app-analyse#abschluss", copy = "Welcher abgeschlossene Lauf gerade gilt, mit Stichtag und Stand.", shiny::uiOutput("status")),
      portelyra_card("Auswertungen des Laufs", help = "app-analyse#abschluss", copy = "Ob Handels- und Marktanalyse dieses Laufs vorliegen.", shiny::uiOutput("analysis_state")),
      portelyra_card("Handelsergebnisse je Zeitraum", help = "app-analyse#abschluss", copy = "Realisierte Ergebnisse aus dem FIFO-Stand des Laufs, je Zeitraum.",
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("trade"))),
      portelyra_card("Kurse des Laufs", help = "app-analyse#abschluss", copy = "Die Kurse, mit denen der Lauf bewertet hat.", shiny::div(class = "pl-table-wrap", shiny::tableOutput("market"))),
      portelyra_card("Positionen zum Stichtag", help = "app-analyse#abschluss", copy = "Bestände und Werte zum Stichtag des Laufs.", shiny::div(class = "pl-table-wrap", shiny::tableOutput("positions"))),
      # Fuer Fachleute (rc.313, bis rc.312 im Cockpit „Abschluss im Detail“): Summen aus den Buchungen, Positionen und
      # Marktwerte des Laufs, auf Wunsch mit exakten Bruechen. Die leere Karte „Exakter EUR-Marktwert“ ist weg (#476).
      shiny::uiOutput("closing_expert")
  )))
)
server <- function(input, output, session) {
  desktop_activity_server_v1(input, output, session, desktop_activity_reader_v1(project_root, runtime$context, "analysis_viewer"))
  desktop_help_server_v1(input, output, session, project_root, "analysis")
  # Neuere Version gefunden (#562 Paket 3): nur update-status.json lesen, nie ins Netz; der Link fuehrt zum Reiter „Programm“ in Data.
  desktop_program_server_v1(input, output, session, runtime$home, desktop_program_version_v1(project_root),
                            desktop_activity_data_link_v1("program", "Ansehen", "pl-activity-link"))
  state <- shiny::reactiveVal(desktop_workflow_display_state_v1())
  load_latest <- function() state(tryCatch(desktop_workflow_display_state_v1(desktop_workflow_read_latest_v1(service)), spot_display_reader_error = function(error) desktop_workflow_display_state_v1(error_code = error$code), error = function(error) desktop_workflow_display_state_v1(error_code = "display_boundary_failed")))
  load_latest(); shiny::observeEvent(input$refresh, load_latest(), ignoreInit = TRUE)
  history <- analysis_history_server_v1(input, output, session, history_read, history_part, history_display,
                                        if (is.null(snapshot_reader)) NULL else snapshot_reader$intraday_read)
  # Umfang je Portfolio (#542): aus den Anzeige-Einstellungen, die die Tageshistorie ohnehin liest - links benannt, abgeschaltete
  # Bausteine ausgeblendet. Ohne veroeffentlichten Umfang NULL: Dann bleibt alles, wie es war.
  scope <- shiny::reactive(desktop_scope_of_v1(history$display()))
  desktop_activity_scope_server_v1(output, scope)
  analysis_scope_server_v1(input, output, session, scope)
  fresh <- display_new_state_server_v1(output, session, "analysis_new_state", history_marker)
  shiny::observeEvent(history$state(), if (!identical(history$state()$kind, "loading")) fresh$mark())
  # Stichtag und Momentaufnahme (rc.313): gelesen erst, wenn der Reiter offen ist; „Neu lesen“ liest erneut.
  analysis_snapshots_server_v1(input, output, session, snapshot_reader, shiny::reactive(input$analysis_tab), shiny::reactive(input$refresh),
                               threshold = function() history_display()$small_holdings_threshold, modules = function() desktop_scope_modules_v1(scope()))
  # Abschluss fuer Fachleute (rc.313, vorher Cockpit): nur mit dem Expertenschalter der Data-App (veroeffentlichte Einstellung).
  expert <- shiny::reactiveVal(FALSE)
  expert_read <- function() expert(isTRUE(tryCatch(history_display()$expert_tools, error = function(error) FALSE)))
  expert_read(); shiny::observeEvent(input$refresh, expert_read(), ignoreInit = TRUE)
  output$closing_expert <- shiny::renderUI({
    if (!isTRUE(expert())) return(NULL)
    shiny::tagList(
      shiny::checkboxInput("closing_exact", "Exakte Brüche anzeigen", FALSE),
      portelyra_card("Summen aus den Buchungen", help = "app-analyse#abschluss", copy = "Je Währung: Umsatz, Einstand des Verkauften, realisierter Gewinn, Erträge und Gebühren.",
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("closing_currencies"))),
      portelyra_card("Marktwerte des Abschlusses", help = "app-analyse#abschluss", shiny::uiOutput("closing_valuation_state"),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("closing_valuation"))),
      portelyra_card("Positionen des Abschlusses", help = "app-analyse#abschluss", copy = "Wie im Lauf gerechnet, auf Wunsch mit exakten Brüchen.",
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("closing_positions"))))
  })
  exact <- shiny::reactive(isTRUE(input$closing_exact))
  cockpit_part <- function(name) { model <- state()$model; if (is.null(model) || is.null(model$cockpit)) NULL else model$cockpit[[name]] }
  output$closing_currencies <- shiny::renderTable(desktop_workflow_labeled_frame_v1(cockpit_part("currency_rows"), exact()), striped = TRUE, bordered = TRUE)
  output$closing_valuation_state <- shiny::renderUI({ model <- state()$model; if (is.null(model) || is.null(model$cockpit)) return(NULL)
    portelyra_status_panel("Bewertung", paste(.desktop_workflow_state_label_v1(model$cockpit$valuation_status), "·", model$cockpit$valuation_currency),
                           tone = if (identical(model$cockpit$valuation_status, "completed")) "neutral" else "warning") })
  output$closing_valuation <- shiny::renderTable({ summary <- cockpit_part("valuation_summary"); if (is.null(summary)) return(data.frame())
    desktop_workflow_labeled_frame_v1(list(summary), exact(), untaxed = desktop_workflow_untaxed_v1(state()$model)) }, striped = TRUE, bordered = TRUE)
  output$closing_positions <- shiny::renderTable(desktop_workflow_labeled_frame_v1(cockpit_part("positions"), exact(), untaxed = desktop_workflow_untaxed_v1(state()$model)), striped = TRUE, bordered = TRUE)
  output$status <- shiny::renderUI(desktop_workflow_status_ui_v1(state(), desktop_scope_single_portfolio_modules_v1(scope())))
  output$analysis_state <- shiny::renderUI({ model <- state()$model; if (is.null(model) || is.null(model$analysis)) return(NULL); portelyra_status_panel("Auswertungen des Laufs", paste("Handelsanalyse", .desktop_workflow_state_label_v1(model$analysis$trade_status), "· Marktanalyse", .desktop_workflow_state_label_v1(model$analysis$market_status)), tone = if (model$analysis$trade_status == "completed" && model$analysis$market_status == "completed") "neutral" else "warning") })
  # Deutsche Spalten, Betraege auf Cent (seit rc.309, wie im Cockpit).
  output$trade <- shiny::renderTable(desktop_workflow_labeled_frame_v1(if (is.null(state()$model)) NULL else state()$model$analysis$trade_periods), striped = TRUE, bordered = TRUE)
  output$market <- shiny::renderTable(desktop_workflow_labeled_frame_v1(if (is.null(state()$model)) NULL else state()$model$analysis$market_history), striped = TRUE, bordered = TRUE)
  output$positions <- shiny::renderTable(desktop_workflow_labeled_frame_v1(if (is.null(state()$model)) NULL else state()$model$analysis$positions, untaxed = desktop_workflow_untaxed_v1(state()$model)), striped = TRUE, bordered = TRUE)
}
shiny::shinyApp(ui, server)
