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
source(file.path(project_root, "apps", "shared", "simple_tax_report_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "simple_tax_report_pdf_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "simple_tax_report_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "tax_event_sheet_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "tax_event_sheet_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "tax_year_documents_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "tax_year_documents_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "tax_annual_statement_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "tax", "tax_ui_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "tax", "tax_projection_view_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "tax", "tax_annual_statement_view_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "tax", "tax_detailed_report_pdf_v1.R"), local = TRUE)
# Der einfache Steuerreport liest Buchungsbestand, FIFO-Stand und Belegangaben direkt und nur lesend.
# Laesst sich der Dienst nicht anlegen, bleibt die uebrige App benutzbar; die Karte sagt es beim Erstellen.
simple_report_service <- tryCatch(new_simple_tax_report_service_v1(project_root, runtime$context), error = function(error) NULL)
# Die Rechenblaetter je Ereignis stehen auf demselben Lot-Nachweis und lesen dazu Steuereinstellungen und Regelmodul.
event_sheet_service <- tryCatch(new_tax_event_sheet_service_v1(project_root, runtime$context), error = function(error) NULL)
# Die Unterlagen des Jahres: Report, Rechenblaetter und die hinterlegten Auszuege als ein Archiv. Es entsteht in einem
# Zwischenverzeichnis der Sitzung - der Datenraum wird auch hier nur gelesen.
year_documents_service <- tryCatch(new_tax_year_documents_service_v1(project_root, runtime$context), error = function(error) NULL)
# Die Jahresrechnung steht auf denselben Ereignissen wie die Rechenblaetter und liest dazu die Angaben je Institut.
annual_statement_service <- tryCatch(new_tax_annual_statement_service_v1(project_root, runtime$context), error = function(error) NULL)
service <- new_desktop_workflow_service_v1(project_root, runtime, "tax_viewer")
# Nur gelesen: ob seit dem gezeigten Abschluss Steuereinstellungen geaendert wurden (#428).
tax_settings_service <- tryCatch(new_tax_ui_service_v1(project_root, dirname(dirname(dirname(runtime_data_space_path(runtime$context)))),
  list(tenant_id = runtime$context$tenant_id, user_id = runtime$context$user_id, data_space_id = runtime$context$data_space_id)), error = function(error) NULL)
# Umfang je Portfolio (#542): aus den veroeffentlichten Anzeige-Einstellungen, mit der Rolle dieser App. Ohne Steuerbericht zeigt die App
# nur eine Statusflaeche; ohne Steuerprojektion entfallen die Karten der Projektion. Ohne veroeffentlichten Umfang bleibt alles stehen.
display_settings_read <- function() spotdisplay::read_display_settings_latest_v1(service$context, project_root)
# Eine Karte, die mit einem abgeschalteten Baustein verschwindet: sichtbar, solange der Server nichts anderes meldet.
tax_scope_gate_v1 <- function(flag, ...) shiny::conditionalPanel(sprintf("output.%s != 'off'", flag), ...)
ui <- portelyra_app_shell(
  "tax", "Portelyra Steuer", "Steuerreport, Jahresrechnung, Rechenblätter und Unterlagen je Jahr – dazu die Steuerprojektion des letzten Portfolioabschlusses.",
  capabilities = c("Liest nur", "Regelmodul je Steuerjahr", "Keine Rechts- oder Steuerberatung"),
  actions = shiny::actionButton("refresh", "Abschluss neu lesen", class = "btn-default"),
  # Aktualisierung, „Läuft gerade“ und Einstellungen links (#540): aus dem veroeffentlichten Stand, die Knoepfe fuehren nach Data.
  sidebar_activity = desktop_activity_sidebar_ui_v1(help_app = "tax", version = desktop_program_version_v1(project_root)),
  shiny::uiOutput("new_state"),
  shiny::uiOutput("tax_scope_state", class = "pl-scope-slot"),
  tax_scope_gate_v1("tax_scope_report", portelyra_card("Steuerreport · einfache Fassung", simple_tax_report_card_ui_v1(), help = "app-steuer#steuerreport--einfache-fassung")),
  tax_scope_gate_v1("tax_scope_report", portelyra_card("Jahresrechnung", tax_annual_statement_card_ui_v1(), help = "app-steuer#jahresrechnung")),
  tax_scope_gate_v1("tax_scope_report", portelyra_card("Rechenblatt je Ereignis", tax_event_sheet_card_ui_v1(), help = "app-steuer#rechenblatt-je-ereignis")),
  tax_scope_gate_v1("tax_scope_report", portelyra_card("Unterlagen des Jahres", tax_year_documents_card_ui_v1(), help = "app-steuer#unterlagen-des-jahres")),
  shiny::uiOutput("tax_scope_projection_state", class = "pl-scope-slot"),
  # Die Tabellen zeigen den letzten Portfolioabschluss - nicht den heutigen Stand der Steuereinstellungen (Festlegung 13.10.2026, #428).
  tax_scope_gate_v1("tax_scope_projection", portelyra_card("Stand des Portfolioabschlusses", shiny::uiOutput("status"), help = "app-steuer#steuerprojektion")),
  tax_scope_gate_v1("tax_scope_projection", portelyra_card("Steuerprojektion je Jahr (Abschluss)", help = "app-steuer#steuerprojektion", copy = "Je Jahr die Summe des Abschlusses.",
    note = portelyra_note_v1(title = "So lesen Sie die Projektion je Jahr", id = "tax-closing-annual",
      "„Unvollständig“ heißt: Ereignisse des Jahres blieben ohne Steuerzahl – meist fehlte beim Abschluss eine Angabe. Nachtragen in Daten → „4. Steuer“ → „Steuerangaben je Jahr“, danach in der App „Daten“ oben rechts „Alles aktualisieren“ starten.",
      "Der Abschluss rechnet ein Jahr wie die Karte „Jahresrechnung“: mit den Zinsen der Cash-Konten, Kapitalerträge je Institut und mit den Verlusttöpfen aus dem Vorjahr."),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("annual")))),
  tax_scope_gate_v1("tax_scope_projection", portelyra_card("Steuerprojektion je Ereignis (Abschluss)", help = "app-steuer#steuerprojektion", copy = "Je Ereignis konservativ – ohne Freistellungsauftrag, Verlustverrechnung und Quellensteuer.",
    note = portelyra_note_v1(title = "So lesen Sie die Projektion je Ereignis", id = "tax-closing-events",
      "Fondsverkäufe stehen mit dem Gewinn nach angesetzten Vorabpauschalen da, die Vorabpauschale selbst als eigene Zeile.",
      "Ohne Häkchen stehen nur Verkäufe und Erträge da. Käufe, Transfers und Zu- und Abgänge ohne Gewinn lösen keine Steuer aus; eine Zeile mit Grund bleibt immer sichtbar."),
    shiny::checkboxInput("tax_events_include_neutral", "Steuerneutrale Vorgänge einbeziehen (Käufe, Transfers, Zu- und Abgänge)", FALSE),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("events")))),
  tax_scope_gate_v1("tax_scope_report", portelyra_card("Hinweis", shiny::textOutput("disclaimer")))
)
server <- function(input, output, session) {
  desktop_activity_server_v1(input, output, session, desktop_activity_reader_v1(project_root, runtime$context, "tax_viewer"))
  desktop_help_server_v1(input, output, session, project_root, "tax")
  # Neuere Version gefunden (#562 Paket 3): nur update-status.json lesen, nie ins Netz; der Link fuehrt zum Reiter „Programm“ in Data.
  desktop_program_server_v1(input, output, session, runtime$home, desktop_program_version_v1(project_root),
                            desktop_activity_data_link_v1("program", "Ansehen", "pl-activity-link"))
  state <- shiny::reactiveVal(desktop_workflow_display_state_v1())
  load_latest <- function() state(tryCatch(desktop_workflow_display_state_v1(desktop_workflow_read_latest_v1(service)), spot_display_reader_error = function(error) desktop_workflow_display_state_v1(error_code = error$code), error = function(error) desktop_workflow_display_state_v1(error_code = "display_boundary_failed")))
  load_latest(); shiny::observeEvent(input$refresh, load_latest(), ignoreInit = TRUE)
  # Neuer Stand veroeffentlicht (#457): Hinweis mit "Neu lesen", sobald sich ein gelesener Bereich seit dem Laden geaendert hat.
  fresh <- display_new_state_server_v1(output, session, "new_state", function() display_new_state_marker_v1(service$context, c("desktop_workflow")),
                                       button = "„Abschluss neu lesen“ oben rechts")
  fresh$mark(); shiny::observeEvent(input$refresh, fresh$mark(), ignoreInit = TRUE)
  # Umfang je Portfolio (#542): gelesen nach dem Seitenaufbau und mit „Abschluss neu lesen“; bis dahin bleibt alles sichtbar.
  scope <- shiny::reactiveVal(NULL)
  read_scope <- function() scope(desktop_scope_of_v1(tryCatch(display_settings_read(), error = function(error) NULL)))
  session$onFlushed(function() read_scope(), once = TRUE)
  shiny::observeEvent(input$refresh, read_scope(), ignoreInit = TRUE)
  desktop_activity_scope_server_v1(output, scope)
  output$tax_scope_report <- shiny::renderText(if (desktop_scope_off_v1(scope(), "tax_report")) "off" else "on")
  output$tax_scope_projection <- shiny::renderText(if (desktop_scope_off_v1(scope(), "tax_report") || desktop_scope_off_v1(scope(), "tax_projection")) "off" else "on")
  shiny::outputOptions(output, "tax_scope_report", suspendWhenHidden = FALSE)
  shiny::outputOptions(output, "tax_scope_projection", suspendWhenHidden = FALSE)
  output$tax_scope_state <- shiny::renderUI(tax_scope_state_ui_v1(scope()))
  output$tax_scope_projection_state <- shiny::renderUI(tax_scope_projection_state_ui_v1(scope()))
  # Beide Hinweise sind leer ausgeblendet (.pl-scope-slot); ohne diese Angabe hielte Shiny sie fuer verborgen und berechnete sie nie.
  shiny::outputOptions(output, "tax_scope_state", suspendWhenHidden = FALSE)
  shiny::outputOptions(output, "tax_scope_projection_state", suspendWhenHidden = FALSE)
  report_card <- simple_tax_report_card_server_v1(input, output, simple_report_service,
    detailed = list(sheets = event_sheet_service, statement = annual_statement_service, render = tax_detailed_report_pdf_v1))
  tax_annual_statement_card_server_v1(input, output, annual_statement_service)
  tax_event_sheet_card_server_v1(input, output, event_sheet_service)
  tax_year_documents_card_server_v1(input, output, list(documents = year_documents_service, report = simple_report_service, sheets = event_sheet_service,
      statement = annual_statement_service, detailed_render = tax_detailed_report_pdf_v1),
    notes = report_card$notes)
  # Die Projektion des letzten Abschlusses - deutsch, auf Cent, mit erklaertem Stand (#428).
  settings_changed <- shiny::reactiveVal(NA)
  shiny::observeEvent(state(), settings_changed(tax_projection_settings_changed_v1(tax_settings_service)), ignoreNULL = FALSE)
  output$status <- shiny::renderUI(tax_projection_status_ui_v1(state(), settings_changed()))
  output$events <- shiny::renderTable(tax_projection_event_frame_v1(tax_projection_event_rows_v1(if (is.null(state()$model)) NULL else state()$model$tax$event_rows,
    isTRUE(input$tax_events_include_neutral))), striped = TRUE, bordered = TRUE)
  output$annual <- shiny::renderTable({
    model <- state()$model
    tax_projection_annual_frame_v1(if (is.null(model)) NULL else model$tax$annual_rows, if (is.null(model)) list() else model$tax$event_rows)
  }, striped = TRUE, bordered = TRUE)
  output$disclaimer <- shiny::renderText(if (desktop_scope_off_v1(scope(), "tax_projection")) "Modellrechnung nach dem gewählten Regelmodul, keine Rechts- oder Steuerberatung."
    else "Modellprojektion nach dem gewählten Regelmodul, keine Rechts- oder Steuerberatung. Ereignis- und Jahresprojektion sind getrennte Rechnungen und werden nicht addiert.")
}
shiny::shinyApp(ui, server)
