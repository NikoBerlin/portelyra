# Portelyra Desktop Product Data entry. It is launched only by scripts/portelyra_desktop.R.
# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
project_root <- getOption("portelyra.desktop.project_root", Sys.getenv("PORTELYRA_DESKTOP_PROJECT_ROOT_INTERNAL", unset = ""))
desktop_home <- Sys.getenv("PORTELYRA_DESKTOP_HOME_INTERNAL", unset = "")
if (!nzchar(project_root)) stop("desktop_product_launcher_required", call. = FALSE)
project_root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
if (!requireNamespace("spotcore", quietly = TRUE) || !requireNamespace("shiny", quietly = TRUE)) stop("desktop_product_dependency_missing", call. = FALSE)
suppressPackageStartupMessages(library(spotcore))
source(file.path(project_root, "packages", "spotcore", "R", "canonical_repository.R"), local = TRUE)
source(file.path(project_root, "packages", "spotcore", "R", "catalog_data_command.R"), local = TRUE)
source(file.path(project_root, "packages", "spotcore", "R", "provider_mapping_data_command_v1.R"), local = TRUE)
source(file.path(project_root, "packages", "spotcore", "R", "transaction_data_command.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "portelyra_ui_shell.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_action_feedback_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "asset_selection_context_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "asset_selection_context_v2.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "asset_selection_context_v3.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "asset_filter_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_workflow_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_workflow_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "data_intraday_snapshot_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "data_portfolio_snapshot_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_portfolio_history_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "data_stands_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_refresh_all_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_refresh_all_store_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_refresh_all_schedule_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_activity_status_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_activity_v1.R"), local = TRUE)
# Rundgang im Demo (#578): nur mit der Option portelyra.desktop.demo eingebunden.
source(file.path(project_root, "apps", "shared", "desktop_tour_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_help_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_transaction_editor_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_asset_activity_editor_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_exact_ratio_presentation_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_cash_coverage_editor_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_asset_maintenance_state_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_table_workbench_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "desktop_product_input_controls_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "desktop_catalog_editor_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_provider_mapping_editor_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_provider_search_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_provider_probe_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_provider_promotion_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_history_plan_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_history_coverage_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_manual_price_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_asset_valuation_timeline_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_activity_reference_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_account_reference_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_institution_tax_settings_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_institution_master_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_investment_scope_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_analysis_settings_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_user_settings_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_storage_retention_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_visibility_v1.R"), local = TRUE)
# Umfang je Portfolio und gefuehrte Einrichtung (#542): Klassen und Bausteine steuern, was angeboten wird und was laeuft.
source(file.path(project_root, "apps", "data", "data_portfolio_configuration_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_protection_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_protection_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_backups_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_backups_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_crypto_valuation_method_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_fifo_wallet_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_stock_split_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_portfolio_snapshot_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_snapshot_publish_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_advance_lump_sum_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_tax_document_import_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_small_holdings_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_statement_archive_v1.R"), local = TRUE)
# Monatlicher Eingang (#513): Belegordner als Quelle, Rezept je Institut.
source(file.path(project_root, "apps", "data", "data_statement_intake_v1.R"), local = TRUE)
# Verwaltung der Leser (rc.380, #486): Version, an Ihren Belegen geprueft, Buchungen je Leser, Selbsttest.
source(file.path(project_root, "apps", "data", "data_statement_readers_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_price_providers_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_plugin_credentials_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_plugin_manager_v1.R"), local = TRUE)
# Reiter „Programm“ (#562, #586): Version und „Neu in dieser Version“ (nur lesend, wie in allen Apps), Browser in den Einstellungen der
# Installation (Programmordner, nicht Datenbestand).
source(file.path(project_root, "apps", "shared", "desktop_program_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "desktop_installation_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_program_v1.R"), local = TRUE)
# Auszuege und Belege werden als Dateien hinterlegt, oft viele auf einmal; Shinys Vorgabe von 5 MB je Auswahl reicht dafuer nicht. Seit rc.276 (#464) ohne Grenze (Shiny: Wert <= 0):
# Jeder Empfaenger prueft selbst, die Auszugsablage etwa 1 GB je Datei, die Grenze des Backups.
options(shiny.maxRequestSize = -1)
source(file.path(project_root, "apps", "data", "data_market_history_carry_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_fx_demand_coverage_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_fx_pair_probe_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_fx_pair_promotion_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_fx_history_review_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_calendar_gap_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_calendar_gap_review_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_reward_daily_close_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_history_review_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_history_review_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_fx_batch_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_fx_batch_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_valuation_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_timeline_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_chain_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_market_worklist_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_asset_worklist_controller_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_asset_center_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_portfolio_csv_exchange_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_statement_import_workspace_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_statement_import_mapping_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "tax", "tax_ui_view_model_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_per_asset_legacy_review_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_per_asset_legacy_review_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_per_asset_legacy_review_adapter_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_activity_draft_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_activity_quick_import_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_per_asset_legacy_review_demo_adapter_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_activity_block_reason_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_net_amount_gross_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_asset_center_filter_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_asset_activity_correction_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "shared", "data_tax_settings_ui_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "tax", "tax_ui_service_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_asset_activity_workflow_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_asset_quantity_scale_revision_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_asset_activity_csv_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_statement_reader_messages_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_cash_statement_import_v1.R"), local = TRUE)
source(file.path(project_root, "apps", "data", "data_securities_statement_import_v1.R"), local = TRUE)
# Experimenteller generischer Leser (#514): Zuordnung und Profil je Format.
source(file.path(project_root, "apps", "data", "data_generic_statement_import_v1.R"), local = TRUE)
runtime <- getOption("portelyra.desktop.runtime")
if (!spotcore::desktop_product_runtime_valid_v1(runtime)) {
  if (!nzchar(desktop_home)) stop("desktop_product_launcher_required", call. = FALSE)
  desktop_home <- normalizePath(desktop_home, winslash = "/", mustWork = TRUE)
  runtime <- spotcore::desktop_product_runtime_load_v1(desktop_home)
}
# Installierte Kursanbieter dieses Bestands (#486 Schritt 3): Jeder Unterprozess, der Kurse abruft, sieht sie; ohne den Ort nur die
# mitgelieferten. "Alles aktualisieren" setzt ihn fuer seine eigenen Unterprozesse ebenso.
Sys.setenv(PORTELYRA_INSTALLED_PRICE_PROVIDERS = file.path(runtime_data_space_path(runtime$context), "price-provider-plugins-v1"))
workflow_service <- new_desktop_workflow_service_v1(project_root, runtime, "viewer")

.desktop_product_force_before_success_v1 <- function(expression, success) {
  value <- force(expression)
  success(value)
}

# Drei Buchungsarten im Reiter Transaktionen (Festlegung 16.10.2026): Non-Cash, Cash (EUR) und Devisen. Devisen buchen mit
# denselben Typen wie Non-Cash (#449) - die Maske nennt sie nur fachlich: Devisenkauf, Devisenverkauf, Zugang aus Ertrag, Uebertrag.
# Buchungsliste in "Manuell" ohne gewaehltes Asset: so viele der neuesten Buchungen (rc.332, #422).
ACTIVITY_ROWS_ALL_LIMIT <- 100L
# Wirkung einer Buchung auf Deutsch (0.3.4, #578): Vorschau und Tabelle zeigten bis dahin die Codes des Kerns (create_lot, exact_ratio).
DESKTOP_ACTIVITY_INVENTORY_EFFECT_LABELS_V1 <- c(increase = "Bestand steigt", decrease = "Bestand sinkt", none = "Bestand unverändert",
                                                 preserve = "Bestand bleibt, die Lots wandern mit")
DESKTOP_ACTIVITY_FIFO_EFFECT_LABELS_V1 <- c(none = "keine", create_lot = "neues Lot", create_lot_then_consume_fee = "neues Lot, Gebühr in Stück daraus",
  create_carried_lot = "übernommenes Lot", consume_fifo = "verbraucht Lots nach FIFO", consume_fifo_and_emit_receipt = "verbraucht Lots nach FIFO, Zugang am Ziel",
  carry_lots_then_consume_fee = "Lots wandern mit, Gebühr in Stück daraus")
DESKTOP_ACTIVITY_COST_AVERAGE_LABELS_V1 <- c(exact_ratio = "exakter Bruch", empty_position = "kein Bestand", basis_missing = "Einstand fehlt")
desktop_activity_event_label_v1 <- function(code) {
  choices <- desktop_activity_type_choices_v1(); hit <- match(code, unname(choices))
  if (length(code) != 1L || is.na(hit)) as.character(code) else names(choices)[[hit]]
}
desktop_activity_type_choices_v1 <- function(mode = "non_cash") {
  if (identical(mode, "fx")) return(c("Devisenkauf (EUR → Fremdwährung)"="buy", "Devisenverkauf (Fremdwährung → EUR)"="sell",
    "Zugang mit Anschaffungskosten (z. B. Zufluss aus Ertrag)"="deposit", "Abgang"="withdrawal", "Übertrag zwischen Fremdwährungskonten"="transfer"))
  c("Kauf"="buy", "Verkauf"="sell", "Bardividende"="dividend", "Stockdividende"="stock_dividend", "Krypto-Reward"="reward",
    "Non-Cash-Zugang"="deposit", "Non-Cash-Abgang"="withdrawal", "Interner Transfer"="transfer")
}
# Text, der nur in einer Buchungsart steht: als span, damit er in Ueberschrift und Absatz passt (conditionalPanel erzeugt ein div;
# "inline" kennt die eingesetzte Shiny-Version nicht). Shiny blendet jedes Element mit data-display-if.
desktop_mode_text_v1 <- function(condition, text) shiny::tags$span(class = "shiny-panel-conditional", `data-display-if` = condition, `data-ns-prefix` = "", text)
# Die Belegkarte liest je Importart ihre Leser (#449, #452): Wertpapiere (mit "Automatisch erkennen"), Krypto-Exporte oder Devisen.
# Die Leser der Institute kommen aus der Leserliste (offered(), #486): Plugins, die in einem Portfolio aktiv sind, mitgelieferte vor
# installierten, je nach Name. Fest im Kern bleiben "Automatisch erkennen", der Krypto-Leser fuer alle Exporte und - zuletzt und
# ausdruecklich so benannt (#514) - die experimentellen generischen Leser. Ohne Leserliste (noch nicht geladen) nur diese.
desktop_offered_reader_choices_v1 <- function(offered, domain, label = function(item) as.character(item$label)) {
  readers <- Filter(function(item) identical(item$domain, domain) && is.character(item$reader_id), if (is.list(offered)) offered$readers else list())
  if (!length(readers)) return(character())
  installed <- vapply(readers, function(item) identical(item$origin, "installed"), logical(1L))
  names <- vapply(seq_along(readers), function(index) paste0(label(readers[[index]]), if (installed[[index]]) " (installiert)" else ""), character(1L))
  ids <- vapply(readers, function(item) as.character(item$reader_id), character(1L))
  order <- order(installed, tolower(names), ids)
  stats::setNames(ids[order], names[order])
}
desktop_securities_import_adapter_choices_v1 <- function(mode = "securities", offered = NULL) {
  plugin <- desktop_offered_reader_choices_v1(offered, mode)
  if (identical(mode, "fx")) return(if (length(plugin)) plugin else if (is.null(offered)) c("Leser werden geladen …" = "")
    else c("Kein Devisen-Leser aktiv – im Reiter „Leser“ aktivieren" = ""))
  if (identical(mode, "crypto")) return(c("Krypto-Börsen und Wallets (CSV-Exporte)"="crypto_exports_v1",
    "Experimentell: generischer Leser für Krypto-CSV (ohne Gewähr)"="generic_crypto_v1"))
  c("Automatisch erkennen"="auto", plugin, "Experimentell: generischer Leser für CSV-Exporte (ohne Gewähr)"="generic_securities_v1")
}
# Reward-Import: je Reward-Leser die Boerse (Institut seines Plugins), aus der Leserliste.
desktop_reward_adapter_choices_v1 <- function(offered = NULL) {
  choices <- desktop_offered_reader_choices_v1(offered, "reward", function(item) as.character(if (is.character(item$institution)) item$institution else item$label))
  if (length(choices)) choices else if (is.null(offered)) c("Leser werden geladen …" = "") else c("Kein Reward-Leser aktiv – im Reiter „Leser“ aktivieren" = "")
}
desktop_transactions_mode_v1 <- function(asset_type) {
  if (!is.character(asset_type) || length(asset_type) != 1L || is.na(asset_type)) return(NULL)
  if (identical(asset_type, "cash")) "cash" else if (identical(asset_type, "fx")) "fx" else "non_cash"
}
# Ohne den Baustein Cash (#542) steht die Wahl nicht da: Es bleibt Non-Cash. Wer ein vorhandenes Cash- oder Devisen-Asset waehlt,
# kommt trotzdem in dessen Erfassung - die Buchungsart folgt dem Asset, nichts verschwindet still.
desktop_transactions_mode_ui_v1 <- function() data_module_only_v1("cash", shiny::div(
  shiny::radioButtons("transactions_mode", "Buchungsart",
    c("Non-Cash · Wertpapiere, Krypto, Rohstoffe …" = "non_cash", "Cash · EUR-Konten" = "cash", "Devisen · Fremdwährungskonten" = "fx"),
    selected = "non_cash", inline = TRUE),
  shiny::p(class = "pl-section-copy", "Wählen Sie oben ein Asset, folgt die Buchungsart seiner Klasse – das EUR-Cash-Asset führt zur Cash-Erfassung, ein Devisen-Asset zu den Devisen.")))
# Reiter Transaktionen (#452, Festlegung 22.10.2026): Unterreiter Manuell / Import / Bestand pruefen. Im Import ein Importer mit
# Auswahl - erst die Art, dann die Quelle mit Version, Pruefstand und den Formaten, die sie liest.
# Seit #542 nur die Arten, die das gewaehlte Portfolio anbietet (`asset_types` seines Umfangs; NULL: alle wie bisher).
desktop_import_kind_choices_v1 <- function(asset_types = NULL) data_portfolio_configuration_import_kinds_v1(c("Wertpapier-Belege" = "securities",
  "Krypto-Exporte" = "crypto", "Rewards" = "rewards", "Cash-Auszüge" = "cash", "Devisen-Belege" = "fx"), asset_types)
desktop_import_kind_ui_v1 <- function() shiny::div(
  shiny::radioButtons("import_kind", "Was importieren?", desktop_import_kind_choices_v1(), selected = "securities", inline = TRUE),
  shiny::uiOutput("import_kind_scope_note"),
  portelyra_note_v1(title = "So läuft ein Import", id = "data-import-steps", shiny::p("Für alle dieselben Schritte: Dateien oder einen Ordner wählen, prüfen (schreibt nichts), Depot oder Konto zuordnen, Vorschau, buchen.",
    "Welche Formate eine Quelle liest, steht unter ihrer Auswahl. Gebucht wird nur Neues; schon Gebuchtes wird erkannt.")))
desktop_fx_mode_note_v1 <- function() portelyra_card("Devisen buchen", help = "app-data#manuell",
  copy = "Devisen (z. B. US-Dollar, Schweizer Franken) sind Assets der Klasse „Devisen“ auf einem Fremdwährungskonto (Kontoart „Fremdwährungskonto (Devisen) / Sonstiges“).",
  note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-fx-booking", paste(
    "Gebucht wird mit den bekannten Typen: Devisenkauf = Kauf (Menge in Fremdwährung, Kurs in EUR je Einheit), Devisenverkauf = Verkauf nach FIFO,",
    "Zufluss aus Ertrag (z. B. Dividende in USD) = Zugang mit dem Kurs der Ertragsabrechnung, Übertrag = Transfer mit Lot-Mitnahme.",
    "Devisengewinne stehen im Steuerreport als private Veräußerungsgeschäfte (Jahresfrist je Lot)."),
    # Nur mit dem Baustein Belege (#583): Ohne ihn gibt es den Unterreiter „Import“ nicht.
    data_module_only_v1("documents", shiny::p("Belege importieren: Unterreiter „Import“ → „Devisen-Belege“ – Kontoauszüge, Devisenbelege und Dividendenabrechnungen der Smartbroker+-Fremdwährungskonten."))))

# Compose each input exactly once; tab navigation never recreates command state.
desktop_data_sections <- list(
  manual = shiny::div(
    id = "asset-activity-editor-anchor", tabindex = "-1",
  portelyra_card(
    "Transaktionen manuell erfassen",
    copy = "Neue Non-Cash-Ereignisse verwenden ausschließlich Asset, Verwahrkonto, exakte Ausführung und FIFO-Nachweis.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-manual-entry", paste(
      "Kauf und Verkauf benötigen kein Cash-Konto und erzeugen keine automatische Cash-Gegenbuchung. Datum, Uhrzeit, Zeitzone und UTC werden getrennt vor der Einmalbestätigung gezeigt.")),
    class = "pl-write-boundary",
    shiny::uiOutput("activity_state"),
    data_expert_only_v1(shiny::tags$details(class="pl-disclosure",
      # Bis zur Grundlagen-Sicht im Cockpit (#478) bleiben Filter und Lesetabellen hier, zugeklappt (Festlegung 22.10.2026);
      # seit rc.309 beim Expertenschalter: Fuer die Buchungen des Assets genuegt deren Tabellenfilter (Festlegung 23.10.2026).
      shiny::tags$summary("Buchungen durchsehen · Filter, Historie und Positionen"),
    shiny::div(
      class = "pl-readonly",
      shiny::tags$h3("Asset-Ansicht filtern"),
      shiny::p(
        class = "pl-section-copy",
        "Diese browserlokale Mehrfachauswahl filtert ausschließlich die drei Lesetabellen. Das Ziel-Asset einer neuen Buchung bleibt davon getrennt und immer genau eins."
      ),
      shiny::div(
        class = "pl-form-grid",
        shiny::selectizeInput(
          "activity_scope_assets", "Manuell einbezogene Assets", choices = character(), multiple = TRUE,
          options = list(
            placeholder = "Ein oder mehrere Assets auswählen …",
            plugins = list("remove_button"), closeAfterSelect = FALSE, maxOptions = 5000
          )
        ),
        shiny::radioButtons(
          "activity_scope_mode", "Auswahlalgebra",
          choices = c(
            "Alle" = "all", "Nur manuell" = "manual", "Nur Filter" = "filter",
            "Manuell ODER Filter" = "union", "Manuell UND Filter" = "intersection"
          ),
          selected = "all", inline = FALSE
        ),
        shiny::checkboxGroupInput(
          "activity_scope_domain", "Asset-Domäne",
          choices = c("Non-Cash" = "noncash", "Cash (hier noch nicht verfügbar)" = "cash"),
          selected = "noncash", inline = TRUE
        )
      ),
      shiny::tags$details(
        class = "pl-disclosure",
        shiny::tags$summary("Weitere Filter · Konten und Ausschlüsse"),
        shiny::div(
          class = "pl-form-grid",
          shiny::selectizeInput(
            "activity_scope_excluded_assets", "Explizit ausgeschlossene Assets", choices = character(), multiple = TRUE,
            options = list(
              placeholder = "Ausschlüsse optional …",
              plugins = list("remove_button"), closeAfterSelect = FALSE, maxOptions = 5000
            )
          ),
          shiny::selectizeInput(
            "activity_scope_accounts", "Konten für den Assetfilter", choices = character(), multiple = TRUE,
            options = list(
              placeholder = "Ein oder mehrere Konten auswählen …",
              plugins = list("remove_button"), closeAfterSelect = FALSE, maxOptions = 5000
            )
          ),
          shiny::radioButtons(
            "activity_scope_account_match", "Kontoverknüpfung",
            choices = c("Irgendeines" = "any", "Alle" = "all", "Keines" = "none"),
            selected = "any", inline = TRUE
          ),
          shiny::radioButtons(
            "activity_scope_account_usage", "Kontobezug",
            choices = c("Aktueller positiver Bestand" = "current", "Historische wirksame Nutzung" = "historical"),
            selected = "current", inline = FALSE
          )
        )
      ),
      shiny::tags$details(
        class = "pl-disclosure",
        shiny::tags$summary("Weitere Filter · Zeitraum und Halten"),
        shiny::div(
          class = "pl-form-grid",
          shiny::checkboxInput(
            "activity_scope_interval_enabled", "Zeitraumfilter verwenden", FALSE
          ),
          desktop_product_empty_date_input_v1(
            "activity_scope_interval_from", "Von (einschließlich)"
          ),
          desktop_product_empty_date_input_v1(
            "activity_scope_interval_to", "Bis einschließlich"
          ),
          shiny::radioButtons(
            "activity_scope_interval_relation", "Zeitraum-Prädikat",
            choices = c(
              "Buchung im Zeitraum" = "activity",
              "Im Zeitraum gehalten" = "holding",
              "Buchung ODER gehalten" = "activity_or_holding",
              "Buchung UND gehalten" = "activity_and_holding"
            ),
            selected = "activity", inline = FALSE
          ),
          shiny::radioButtons(
            "activity_scope_holding_mode", "Halten bedeutet",
            choices = c(
              "Irgendwann im Zeitraum" = "any_time",
              "Zu Beginn" = "at_start",
              "Am Ende" = "at_end",
              "Durchgehend" = "throughout"
            ),
            selected = "any_time", inline = FALSE
          )
        ),
        shiny::p(
          class = "pl-section-copy",
          "Der Filter „Buchung“ nutzt Kalenderdaten einschließlich der Grenzen. „Gehalten“ benötigt den bereits abgeschlossenen frischen FIFO-v2-Stand; dieser Filter startet keine Berechnung. Ereignisse vor „Von“ dienen nur als Anfangsstand."
        )
      ),
      shiny::div(
        class = "pl-editor-actions",
        shiny::actionButton(
          "activity_scope_reset", "Filter vollständig zurücksetzen", class = "btn-default"
        )
      ),
      shiny::p(
        class = "pl-section-copy",
        "Setzt ausschließlich den browserlokalen Lesefilter auf Alle / Non-Cash zurück. Das separate Ziel-Asset des Buchungsformulars bleibt unverändert; es startet weder Berechnung noch Kursabruf noch Schreiben in den Bestand."
      ),
      shiny::uiOutput("activity_scope_state"),
      shiny::tags$h4("Analytischer Bestand · eigener Filterumfang"),
      shiny::tableOutput("activity_positions"),
      shiny::tableOutput("activity_custody_positions"),
      shiny::conditionalPanel(
        "input.activity_scope_interval_enabled",
        shiny::tags$h4("Zeitraum- und Anfangsstand je Portfolio × Asset"),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("activity_interval_states"))
      ),
      shiny::actionButton(
        "activity_scope_focus_form", "Zum Buchungsformular", class = "btn-default",
        `aria-controls` = "asset-activity-command-form-anchor",
        onclick = paste0(
          "var target=document.getElementById('asset-activity-command-form-anchor');",
          "if(target){target.scrollIntoView({behavior:'smooth',block:'start'});target.focus({preventScroll:true});}"
        )
      )
    ),
    )),
    # Wirkt auf die Tabellen des Bereichs darueber und den FIFO-Stand; mit ihm beim Expertenschalter (#492).
    data_expert_only_v1(shiny::checkboxInput("activity_show_exact_ratios", "Exakte Brüche anzeigen", FALSE),
    shiny::p(class="pl-section-copy", "Beträge erscheinen auf Cent gerundet mit ihrer Währung, Kurse mit höchstens acht Nachkommastellen, Stückzahlen ohne Nullen am Ende; die Checkbox zeigt die Werte und Brüche unverändert, wie der Rechenkern sie führt.")),
    # Die Buchungen des gewaehlten Assets, auswaehlbar, unter dem Formular. Davor
    # lagen sie eingeklappt hinter einem Aufklapper, und gewaehlt wurde ueber ein
    # Dropdown mit sehr vielen Eintraegen - obwohl die Tabelle daneben stand,
    # und so kaum
    # durchfuehrbar (#424).
    shiny::tags$h3("Buchungen dieses Assets · neueste zuerst"),
    shiny::p(class="pl-section-copy",
      "Keine Zeile gewählt heißt: neue Buchung anlegen. Eine Zeile gewählt: bearbeiten oder stornieren.",
      " Ein Klick auf die Zeile genügt."),
    shiny::uiOutput("activity_rows_filter"),
    shiny::div(class="pl-editor-actions",
      shiny::checkboxInput("activity_rows_superseded","Ersetzte mitzeigen",FALSE),
      shiny::actionButton("activity_correction_refresh","Buchungen neu lesen",class="btn-default"),
      # Leeren im Browser, damit die Kaestchen und der Eingabewert gleichzeitig
      # zurueckgehen - ein Serverlauf dazwischen wuerde beides auseinanderbringen.
      shiny::tags$button(type="button",class="btn btn-default",
        onclick=paste0("document.querySelectorAll('#activity_rows_table input[data-row]')",
          ".forEach(function(b){b.checked=false;});",
          "Shiny.setInputValue('activity_rows_selected',[],{priority:'event'});return false;"),
        "Auswahl leeren")),
    shiny::uiOutput("activity_rows_hint"),
    shiny::uiOutput("activity_rows_table"),
    # Belegangaben zur gewaehlten Buchung: Transaktions-ID, Adresse, Notiz (rc.246).
    shiny::uiOutput("activity_reference_panel"),
    # Sammelbearbeitung: mit "weiter" von Buchung zu Buchung, jede aendern,
    # bestaetigen, stornieren oder unveraendert lassen.
    #
    # Kein neuer Schreibweg: Die Reihe stellt jeweils genau eine Buchung in die
    # bestehende Maske, und jede Aenderung geht durch dieselbe Vorschau und
    # dieselbe Einmalbestaetigung wie eine einzelne Korrektur. Der Kern kann
    # ohnehin nichts anderes - eine Vorschau traegt entweder n Stornos oder genau
    # einen Ersatz (#424).
    shiny::conditionalPanel("output.activity_sequence_mode == 'offer'",
      shiny::div(class="pl-editor-actions",
        shiny::actionButton("activity_sequence_start","Einzeln durchgehen",class="btn-default"))),
    shiny::conditionalPanel("output.activity_sequence_mode == 'running'",
      shiny::uiOutput("activity_sequence_state"),
      shiny::div(class="pl-editor-actions",
        shiny::actionButton("activity_sequence_skip","Unverändert lassen · weiter",class="btn-default"),
        shiny::actionButton("activity_sequence_stop","Reihe beenden",class="btn-default"))),
    shiny::uiOutput("activity_sequence_report"),
    data_expert_only_v1(shiny::tags$details(class="pl-disclosure",
      shiny::tags$summary("Vollständige Historie mit allen Rechenfeldern"),
      shiny::uiOutput("activity_history_scope"),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("activity_history")),
      shiny::p(class="pl-section-copy","Bestehende Buchung korrigieren oder stornieren: Der Vorgänger bleibt in seiner unveränderlichen Generation erhalten. Kein Gegengeschäft und kein automatisches Cash."),
      shiny::checkboxInput("activity_correction_focus_asset","Auswahl auf das im Formular gewählte Asset eingrenzen",FALSE),
      shiny::checkboxInput("activity_selection_discard","Nicht gespeicherte Formulareingaben für den Auswahlwechsel verwerfen",FALSE),
      shiny::actionButton("activity_correction_load","Vorgänger als Entwurf laden",class="btn-default")
    )),
    shiny::uiOutput("activity_workflow_state"),
    shiny::conditionalPanel("output.activity_workflow_action == 'correct' || output.activity_workflow_action == 'void'",
      shiny::selectInput("activity_correction_action","Aktion für ausgewählte Buchung",c("Bearbeiten"="correct","Stornieren"="void"))
    ),
    shiny::div(
      id = "asset-activity-command-form-anchor", tabindex = "-1",
      shiny::tags$h3("Gemeinsame Transaktionsmaske · genau ein Non-Cash-Asset"),
      portelyra_note_v1(title = "So erfassen Sie eine Buchung", id = "data-manual-steps", shiny::p("Zuerst Ereignis, Ziel und Zeitpunkt wählen. Danach erscheinen nur die dafür benötigten Mengen- und Wertfelder. Dezimalkomma und Dezimalpunkt sind zulässig; gespeichert wird ohne Rundung in kanonischer Schreibweise.")),
    # Asset und Portfolio sind Kontext, nicht Eingabe. Sie kamen bis rc.225 als
    # zweites, frei belegbares Dropdown im Formular vor - und genau diese zweite
    # Stelle hat zweimal eine Buchung unsichtbar gemacht, weil Tabelle und
    # Formular auf verschiedene Assets zeigten. Jetzt bestimmt allein die Suche des Asset-Centers den
    # Kontext; das Formular zeigt ihn nur noch an (#424).
    #
    # Die beiden Eingaben bleiben als stille Traeger bestehen: Die nativen
    # Kommandos sprechen Portfolio und Asset ueber Editor-Refs an, und diese Refs
    # werden hier serverseitig gesetzt. Bedienbar sind sie nicht mehr.
    shiny::uiOutput("activity_target_context"),
    shiny::div(class="pl-context-carrier", style="display:none",
      shiny::selectInput("activity_portfolio", "Portfolio", c("Bitte wählen"="")),
      shiny::selectInput("activity_asset", "Asset", c("Bitte wählen"=""))),
    shiny::conditionalPanel("output.activity_workflow_action == 'create' || output.activity_workflow_action == 'correct'",
    # Je Buchungsart nur die Felder, die der Kern dort liest (#422): Die Bedingungen leitet
    # desktop_product_activity_field_v1 aus desktop_product_activity_relevant_fields_v1 ab, dieselbe Liste, nach der
    # activity_form() Ungelesenes leer schickt. Ausgeblendete Felder behalten im Browser ihren Wert.
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("activity_type", "Ereignis", desktop_activity_type_choices_v1()),
      shiny::selectInput("activity_account", "Konto / Wallet", c("Bitte wählen"="")),
      desktop_product_activity_field_v1("related_account", shiny::selectInput("activity_related_account", "Zielkonto / Ziel-Wallet", c("Bitte wählen"=""))),
      desktop_product_activity_field_v1("source_asset", shiny::selectInput("activity_source_asset", "Ursprüngliches Asset", c("Bitte wählen"=""))),
      shiny::selectInput("activity_time_evidence", "Zeitangabe", c("Datum und genaue Uhrzeit"="exact", "Nur Datum bekannt"="date_only")),
      desktop_product_empty_date_input_v1("activity_date", "Transaktionsdatum"),
      shiny::conditionalPanel("input.activity_time_evidence == 'exact'",shiny::textInput("activity_time", "Lokale Uhrzeit", "", placeholder="HH:MM oder HH:MM:SS")),
      shiny::textInput("activity_zone", "Zeitzone", "Europe/Berlin", placeholder="z. B. Europe/Berlin"),
      desktop_product_activity_field_v1("quantity", shiny::textInput("activity_quantity", "Menge", "")),
      desktop_product_activity_field_v1("eligible_quantity", shiny::textInput("activity_eligible_quantity", "Dividendenberechtigte Menge", "")),
      desktop_product_activity_field_v1("amount_mode", shiny::selectInput("activity_amount_mode", "Wert eingeben als", c("Menge × Stückpreis"="quantity_unit_price", "Brutto-Gesamtbetrag"="gross_total", "Nicht anwendbar"="not_applicable"))),
      desktop_product_activity_field_v1("unit_price", shiny::textInput("activity_unit_price", "Stückpreis / Wert je Einheit", "")),
      desktop_product_activity_field_v1("gross_total", shiny::textInput("activity_gross_total", "Brutto-Gesamtbetrag", "")),
      # Netto eintragen, brutto buchen: nur bei der Dividende. Der Steuersatz ist der,
      # der im Nettobetrag schon abgezogen ist; gerechnet wird Netto / (1 - Satz/100).
      desktop_product_activity_field_v1("net_total", shiny::textInput("activity_net_total", "Netto-Gesamtbetrag", "")),
      desktop_product_activity_field_v1("net_unit_price", shiny::textInput("activity_net_unit_price", "Netto-Stückpreis", "")),
      desktop_product_activity_field_v1("net_tax_rate",
        shiny::textInput("activity_net_tax_rate", "Steuersatz in %, im Nettobetrag schon abgezogen", "", placeholder = "z. B. 26,375"),
        shiny::div(class = "pl-field-hint", shiny::textOutput("activity_net_gross_hint"))),
      desktop_product_activity_field_v1("monetary_fee", shiny::textInput("activity_monetary_fee", "Geldgebühr (optional)", "")),
      # Anlass und urspruengliche Anschaffungszeit sind bei Ein- und Auslieferung Pflicht; bis rc.329 lagen sie im Aufklapper.
      desktop_product_activity_field_v1("movement_context", shiny::selectInput("activity_movement_context", "Anlass", c("Nicht anwendbar"="not_applicable", "Unklassifiziert"="unclassified", "Schenkung"="gift", "Erbschaft"="inheritance", "Schuldentilgung"="debt_settlement", "Spende"="donation", "Zahlung"="payment", "Verwahrausgang"="custody_exit", "Sonstiges"="other"))),
      desktop_product_activity_field_v1("acquisition",
        shiny::selectInput("activity_acquisition_evidence", "Ursprüngliche Anschaffungszeit", c("Nicht anwendbar"="not_applicable", "Nur Datum"="date_only", "Exakt"="exact")),
        shiny::conditionalPanel("input.activity_acquisition_evidence != 'not_applicable'",desktop_product_empty_date_input_v1("activity_acquisition_date", "Ursprüngliches Anschaffungsdatum"),shiny::textInput("activity_acquisition_zone", "Ursprüngliche Zeitzone", "")),
        shiny::conditionalPanel("input.activity_acquisition_evidence == 'exact'",shiny::textInput("activity_acquisition_time", "Ursprüngliche Uhrzeit", "", placeholder="HH:MM oder HH:MM:SS"),shiny::textInput("activity_acquisition_utc", "Ursprünglicher UTC-Zeitpunkt", ""))),
      # Belegangaben gleich beim Erfassen (#439). Sie gehen in den Beleg-Speicher neben dem Bestand; bei einer Korrektur
      # zieht der Bereich "Beleg" der gewaehlten Buchung sie mit, deshalb stehen die Felder nur bei der Neuanlage.
      shiny::conditionalPanel("output.activity_workflow_action == 'create'",
        shiny::textInput("activity_transaction_id", "Transaktions-ID (optional)", "", placeholder = "Order-, Vorgangs- oder Transaktionsnummer")),
      shiny::conditionalPanel("output.activity_workflow_action == 'create' && output.activity_asset_is_crypto == 'yes'",
        shiny::textInput("activity_counterparty_address", "Adresse der Gegenseite (optional)", "", placeholder = "Wallet-Adresse oder Public Key"))
    ),
    shiny::textOutput("activity_asset_fee_notice"),
    shiny::tags$details(class="pl-disclosure",
      shiny::tags$summary("Weitere Angaben · Gebühr in Stücken, Basis und Zeitprüfung"),
      desktop_product_activity_field_v1("asset_fee", shiny::p(class="pl-section-copy", "Eine Gebühr in Asset-Einheiten nur eintragen, wenn tatsächlich Stücke oder Coins als Gebühr berechnet wurden. Dieselbe Gebühr nicht zusätzlich als Geldgebühr erfassen.")),
      shiny::div(class="pl-form-grid",
        desktop_product_activity_field_v1("asset_fee", shiny::textInput("activity_asset_fee", "Gebühr in Asset-Einheiten (optional)", "")),
        desktop_product_activity_field_v1("basis_mode", shiny::selectInput("activity_basis_mode", "FIFO-Nachweis der Anschaffung", c("Trade abgeleitet"="derived_trade", "Bewertung als Basis bestätigt"="valuation_confirmed_as_basis", "Basis explizit belegt"="provided_basis", "Basis fehlt"="basis_missing", "Nicht anwendbar"="not_applicable"))),
        desktop_product_activity_field_v1("provided_basis", shiny::textInput("activity_provided_basis", "Explizite FIFO-Basis", "")),
        shiny::conditionalPanel("input.activity_time_evidence == 'exact'",shiny::textInput("activity_utc", "Resultierender UTC-Zeitpunkt (optional zur Gegenprüfung)", "", placeholder="wird serverseitig aus Datum, Uhrzeit und Zeitzone ermittelt"))
      ),
      shiny::p(class="pl-section-copy","Anschaffungsbasis, Bewegungs- und Herkunftsnachweise werden nie aus verborgenen Standardwerten erfunden. Nicht anwendbare Felder bleiben explizit nicht anwendbar.")
    ),
    ),
    # Hinweis, keine Sperre: Wer eine Buchung vor dem erklaerten Pflegestand
    # nachtraegt, aendert eine abgeschlossene Historie; das entspricht einer Korrektur (#423).
    shiny::uiOutput("activity_maintenance_hint"),
    shiny::conditionalPanel("output.activity_workflow_action == 'create'",
    shiny::uiOutput("activity_guided_hint"),
    shiny::div(class = "pl-editor-actions",
      shiny::uiOutput("activity_context_block"),
      shiny::actionButton("activity_prepare", "Transaktion prüfen", class = "btn-default"),
      shiny::actionButton("activity_execute", "Speichern", class = "btn-primary"),
      shiny::actionButton("activity_draft_discard", "Eingaben verwerfen", class = "btn-default")
    ),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("activity_preview"))
    ),
    shiny::uiOutput("activity_command_feedback"),
    # Die Skalenfelder standen dauerhaft im Formular, obwohl sie nur bei einer
    # Warnung etwas bedeuten. Alles
    # Speziellere soll nicht dauerhaft angezeigt werden.
    # Jetzt erscheinen Bestaetigung und Ausfuehrung nur, wenn eine Warnung
    # vorliegt; die seltene Wiederaufnahme liegt hinter einem Aufklapper und
    # bleibt damit erreichbar, ohne im Weg zu stehen (#424).
    shiny::uiOutput("activity_scale_warning"),
    shiny::conditionalPanel("output.activity_scale_state == 'warned'",
      shiny::div(class = "pl-editor-actions",
        shiny::checkboxInput("activity_scale_confirm", "Mengenskala wie gewarnt erhöhen; Mengen werden nicht gerundet", FALSE),
        shiny::actionButton("activity_scale_execute", "Skala erhöhen und Generation aktualisieren", class = "btn-primary")
      )
    ),
    data_when_needed_v1("scale_resume", shiny::tags$details(class="pl-disclosure",
      shiny::tags$summary("Unterbrochene Skalenanpassung fortsetzen"),
      shiny::p(class="pl-section-copy","Nur nötig, wenn eine Skalenanhebung zwischen Katalogschreibung und Generationsabschluss abgebrochen ist. Lesen schreibt nichts."),
      shiny::div(class = "pl-editor-actions",
        shiny::actionButton("activity_scale_pending_refresh", "Unterbrochene Skalenanpassungen lesen", class = "btn-default"),
        shiny::selectInput("activity_scale_resume_ref", "Unterbrochene Skalenanpassung", c("Bitte wählen" = "")),
        shiny::actionButton("activity_scale_resume", "Skalenanpassung fortsetzen", class = "btn-default")
      )
    ))
    ),
    shiny::tags$hr(),
    shiny::conditionalPanel("output.activity_workflow_action == 'correct' || output.activity_workflow_action == 'void'",
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("activity_correction_prepare","Korrektur-/Storno-Vorschau",class="btn-default"),
      shiny::checkboxInput("activity_correction_confirm","Auswahl und Vorschau geprüft – genau diese Änderung einmalig bestätigen",FALSE),
      shiny::actionButton("activity_correction_execute","Bestätigt anwenden",class="btn-primary")
    ),
    shiny::uiOutput("activity_correction_state"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("activity_correction_preview")),
    shiny::uiOutput("activity_batch_review")
    ),
    shiny::uiOutput("correction_action_feedback"),
    shiny::uiOutput("activity_release_feedback"),
    # Der Wiederaufnahmeweg unterbrochener Buchungen bleibt auch ohne Schalter erreichbar (#452): Der Verweis blendet die
    # Expertenwerkzeuge fuer diese Sitzung ein und springt erst danach zu den offenen Vorgaengen.
    shiny::tags$a(href='#activity_pending_heading',onclick="if(window.Shiny&&Shiny.setInputValue)Shiny.setInputValue('data_expert_tools_reveal',1);setTimeout(function(){var h=document.getElementById('activity_pending_heading');for(var p=h;p;p=p.parentElement){if(p.tagName==='DETAILS')p.open=true;}h.scrollIntoView({block:'center'});h.focus();},300);",'Unklarer Ausgang? Offene Vorgänge prüfen – nicht neu anlegen.'),
    # Begriffe statt Kuerzel (#422, Festlegung 27.10.2026): "FIFO v2 und Cost Average" sagte nicht, was in der Tabelle steht.
    shiny::tags$h3("Bestand dieses Assets · Stück, Einstandswert und realisierte GuV"),
    shiny::uiOutput("activity_context_state"),
    portelyra_note_v1(title = "So lesen Sie den Bestand", id = "data-asset-state", shiny::tags$ul(
      shiny::tags$li("Menge und Einstandswert: was Sie von diesem Asset noch halten und was diese Stücke gekostet haben, über alle Konten zusammen."),
      shiny::tags$li("Ø Einstandskurs: Einstandswert geteilt durch die Menge."),
      # FIFO-Wallet (#508) und Durchschnitt je Coin und Wallet (rc.294) rechnet der Kern mit; der Text sagt es dazu.
      shiny::tags$li("Verbraucht wird je Konto bzw. FIFO-Wallet: Ein Verkauf nimmt die ältesten Stücke (FIFO). Sind mehrere Konten zu einem FIFO-Wallet zusammengefasst, zählen ihre Stücke gemeinsam. Ein Transfer nimmt die Stücke samt Anschaffungsdatum und Anschaffungskosten mit."),
      shiny::tags$li("Bei Coins mit Durchschnittsmethode (Stammdaten → FIFO-Wallet → „Krypto · Wertermittlung je Wallet“) zählen für die Kosten eines Verkaufs die Durchschnittskosten des Wallets; die Haltefrist folgt weiter FIFO."),
      shiny::tags$li("Realisiert: Erlös, Einstandswert und GuV der schon verkauften Stücke, vor Steuern."),
      shiny::tags$li("„Bestand je Konto / Wallet“ darunter zeigt jedes Konto mit Bestand; das Konto im Formular ist markiert – so viel lässt sich dort verkaufen oder übertragen. Die Summe der Konten muss den Bestand darüber ergeben. Analytische Filter ändern diese Kontrolle nicht."))),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("activity_context_positions")),
    # Je Konto statt nur das gewaehlte (rc.335, Festlegung 27.10.2026): Bestandskontrolle ueber mehrere Konten und Wallets.
    shiny::tags$h3("Bestand je Konto / Wallet"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("activity_context_custody_positions")),
    shiny::uiOutput("activity_context_custody_check"),
    # Der Pruefstempel steht beim Bestand, an dem er geprueft wird. Bis rc.233 war
    # der Pflegestand nur im Abschluss zu setzen, zwei Reiter entfernt von der
    # Stelle, an der die Buchungen nachgetragen werden (Festlegung vom 10.10.2026).
    # Die Sammelsetzung ueber alle Paare und das Zuruecknehmen bleiben dort.
    shiny::tags$h3("Pflegestand dieses Assets · Prüfstempel"),
    shiny::uiOutput("activity_stamp_state"),
    shiny::conditionalPanel("output.activity_stamp_mode == 'ready'",
      shiny::div(class="pl-table-wrap",shiny::tableOutput("activity_stamp_table")),
      shiny::div(class="pl-form-grid",
        shiny::checkboxGroupInput("activity_stamp_pairs","Geprüfte Konten",choices=character()),
        desktop_product_empty_date_input_v1("activity_stamp_through","Geprüft bis einschließlich")),
      shiny::div(class="pl-editor-actions",
        shiny::actionButton("activity_stamp_prepare","Stempel prüfen",class="btn-default"),
        shiny::conditionalPanel("output.activity_stamp_mode_preview == 'ready'",
          shiny::actionButton("activity_stamp_apply","Stempel setzen",class="btn-primary")),
        shiny::span(class="pl-field-hint","Erklärt: bis zu diesem Tag mit dem Broker abgeglichen, alle Bewegungen erfasst. Rewards pflegt der Reward-Import."))),
    shiny::uiOutput("activity_stamp_preview"),
    shiny::uiOutput("activity_stamp_feedback"),
    # pl-lazy: Zugeklappt wird die Tabelle nicht gebaut. Seit die Buchungsliste beim
    # Start laedt, traefe das sonst jeden Sitzungsstart.
    data_expert_only_v1(shiny::tags$details(class="pl-lazy",id="activity_correction_history_details",shiny::tags$summary("Korrektur-/Stornohistorie"),
      shiny::div(class="pl-editor-actions",
        shiny::actionButton("activity_correction_history_clear","Anzeige leeren",class="btn-default"),
        shiny::actionButton("activity_correction_history_show","Anzeige wieder einblenden",class="btn-default")),
      shiny::uiOutput("activity_correction_history_state"),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("activity_correction_history")),
      shiny::p('Generationsbelege sind keine Wiederaufnahmefreigabe. Eine unterbrochene Aktivierung unter „Offene Vorgänge“ abgleichen.'),
      shiny::p('„Anzeige leeren“ blendet ausschließlich diese Tabelle aus. Die Generationsbelege bleiben unverändert erhalten und sind jederzeit wieder einblendbar; der Buchungsbestand wird nicht verändert.'))),
    # Der Rechenstand (bis rc.330 "Deterministischer FIFO-v2-/Realisierter-State" mit vier Knoepfen) steht seit rc.331 unter
    # "Bestand pruefen" (#422): Jede Buchung rechnet ihn ohnehin selbst nach; "State lesen" und "Betroffene Welten
    # aktualisieren" doppelten dort "Rechenstand pruefen" und "Nachrechnen".
    data_expert_only_v1(shiny::tags$details(id="activity-csv-exchange",class="pl-disclosure",
      shiny::tags$summary("Portelyra-Buchungsliste (CSV) exportieren oder einlesen"),
      shiny::p(class="pl-section-copy",shiny::strong("Eigenes Format von Portelyra – keine Datei einer Bank, eines Brokers oder einer Börse."),
        data_module_only_v1("documents", " Deren Belege und Exporte liest der Reiter „Import“.", inline = TRUE)),
      shiny::p(class="pl-section-copy","Die Datei lässt sich außerhalb der App ansehen und ergänzen. Beim erneuten Einlesen werden unveränderte Zeilen erkannt und nicht doppelt gebucht; nur neue Zeilen werden übernommen. Enthält eine Zeile einen Fehler, wird nichts übernommen und jede fehlerhafte Zeile mit Grund benannt."),
      shiny::div(class="pl-editor-actions",
        shiny::downloadButton("activity_csv_export_asset","Buchungen dieses Assets exportieren"),
        shiny::downloadButton("activity_csv_export_all","Alle Buchungen exportieren"),
        shiny::downloadButton("activity_csv_template","Leere Vorlage")),
      shiny::tags$details(id="activity-csv-guide",class="pl-disclosure",
        shiny::tags$summary("Anleitung: CSV richtig bearbeiten"),
        shiny::tags$h4("1 · Werkzeug"),
        shiny::tags$ul(
          shiny::tags$li("Am sichersten mit einem Texteditor (z. B. gedit). Tabellenprogramme verändern Zahlen beim Speichern oft unbemerkt."),
          shiny::tags$li("LibreOffice Calc: beim Öffnen im Importdialog Trennzeichen „Komma“ wählen, alle Spalten markieren und Spaltentyp „Text“ setzen. Speichern als CSV, Zeichensatz UTF-8, Feldtrenner Komma."),
          shiny::tags$li("Excel: Datei über „Daten → Aus Text/CSV“ öffnen und alle Spalten als Text laden; nicht per Doppelklick öffnen.")),
        shiny::tags$h4("2 · Zahlen – der heikelste Punkt"),
        shiny::tags$ul(
          shiny::tags$li(shiny::HTML("Dezimal<strong>punkt</strong>, kein Komma: <code>0.495</code>, nicht <code>0,495</code>.")),
          shiny::tags$li(shiny::HTML("Keine Tausendertrennzeichen: <code>2100.5</code>, nicht <code>2.100,5</code>. Ein deutsches Tabellenprogramm liest <code>0.495</code> sonst als 495.")),
          shiny::tags$li(shiny::HTML("Nichts runden oder abschneiden: Reward-Kurse wie <code>1234.56789012345678901</code> vollständig lassen.")),
          shiny::tags$li(shiny::HTML("Keine überflüssigen Nullen: <code>2100.5</code> statt <code>2100.50</code>, <code>4</code> statt <code>4.0</code>. Kein Vorzeichen, kein Exponent (<code>1e2</code>).")),
          shiny::tags$li("Leeres Feld heißt „nicht angegeben“, nicht 0.")),
        shiny::tags$h4("3 · Neue Zeile anlegen"),
        shiny::tags$ul(
          shiny::tags$li("Eine vorhandene Zeile desselben Typs kopieren und nur Datum, Uhrzeit, Menge, Preis, Gebühr und Konto ändern."),
          shiny::tags$li(shiny::HTML("<code>row_key</code> neu vergeben: Kleinbuchstaben, Ziffern, _ oder -, mindestens 3 Zeichen, z. B. <code>neu_001</code>. <code>import_key</code> unverändert lassen.")),
          shiny::tags$li(shiny::HTML("Datum <code>JJJJ-MM-TT</code>, Uhrzeit <code>HH:MM:SS</code>. Ohne Uhrzeit: <code>event_time_evidence</code> = <code>date_only</code> und <code>local_time</code> leer.")),
          shiny::tags$li(shiny::HTML("<code>basis_evidence_mode</code>: Kauf <code>derived_trade</code>, Verkauf und Transfer <code>not_applicable</code>, Reward <code>valuation_confirmed_as_basis</code>.")),
          shiny::tags$li(shiny::HTML("Gebühr in EUR: <code>fee_role</code> = <code>monetary</code>, <code>fee_currency</code> = <code>EUR</code>. Ohne Gebühr: <code>none</code> und beide Gebührenfelder leer."))),
        shiny::tags$h4("4 · Vorhandene Zeilen"),
        shiny::p("Zeilen mit „bestand_…“ stammen aus dem Export und bleiben unverändert. Korrekturen bitte über „Buchung korrigieren“ – eine geänderte Zeile blockiert den Import."),
        shiny::p("Ohne „Neue Zeilen übernehmen“ wird nichts gebucht. Die Vorschau lässt sich gefahrlos beliebig oft erstellen.")),
      shiny::div(class="pl-editor-actions",
        shiny::fileInput("activity_csv_file","CSV-Datei zum Import auswählen",accept=".csv",multiple=FALSE),
        shiny::actionButton("activity_csv_inspect","Datei prüfen",class="btn-default"),
        shiny::conditionalPanel("output.activity_csv_mapping_needed == 'yes'",shiny::actionButton("activity_csv_prepare","Zuordnung übernehmen",class="btn-default")),
        shiny::actionButton("activity_csv_execute","Neue Zeilen übernehmen",class="btn-primary")),
      shiny::uiOutput("activity_csv_state"),
      shiny::uiOutput("activity_csv_scope_note"),
      shiny::uiOutput("activity_csv_mappings"),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("activity_csv_preview")))),
    # Steht ausserhalb des CSV-Bereichs (#492): Der ist Expertenwerkzeug, die Wiederaufnahme erscheint von selbst.
    data_when_needed_v1("csv_resume", shiny::tags$details(class="pl-disclosure",open=NA,shiny::tags$summary("Unterbrochenen Import fortsetzen"),
      shiny::div(class="pl-editor-actions",
        shiny::actionButton("activity_csv_resume_refresh","Unterbrochene Importe lesen",class="btn-default"),
        shiny::selectInput("activity_csv_resume_ref","Unterbrochener Import",c("Bitte wählen"="")),
        shiny::actionButton("activity_csv_resume","Import fortsetzen",class="btn-default"))))
   )),
  quick_import = shiny::div(
    shiny::p(class="pl-section-copy","Ältere, tolerante Importwege: Quick Import erzeugt ActivityDrafts, die einzeln übernommen werden. Für den Alltag den Reiter „Import“ oder die „Portelyra-Buchungsliste (CSV)“ unter „Manuell“ verwenden."),
    shiny::tags$h3("Quick Import / Export · portelyra-activity.csv"),
    shiny::p(class="pl-section-copy","Tolerante Zeilen werden als dauerhafte Buchungsentwürfe gespeichert. Nach der Prüfung wird jeder Portfolio-, Konto- und Asset-Schlüssel ausdrücklich einer browserlokalen Auswahl aus dem Register zugeordnet. Zeilen mit fehlenden Angaben bleiben im Zustand „Angaben fehlen“; importiert werden ausschließlich erneut validierte, bereite Zeilen."),
    shiny::div(class="pl-form-grid",
      shiny::selectInput("activity_quick_portfolio","Standardportfolio für leere portfolio_key",c("Bitte wählen"="")),
      shiny::selectInput("activity_quick_asset","Vorauswahl für einen einzelnen Asset-Schlüssel",c("Bitte wählen"="")),
      shiny::selectInput("activity_quick_default_account","Standardkonto für leere account_key",c("Bitte wählen"="")),
      shiny::fileInput("activity_quick_file","portelyra-activity.csv auswählen",accept=".csv",multiple=FALSE)
    ),
    shiny::uiOutput("activity_quick_mapping_ui"),
    shiny::div(class="pl-form-grid",
      shiny::textInput("activity_quick_profile_label","Name des Zuordnungsprofils","Standardprofil"),
      shiny::checkboxInput("activity_quick_profile_standard","Als Standardprofil dieses Registerkontexts speichern",TRUE),
      shiny::selectInput("activity_quick_profile_select","Gespeichertes Zuordnungsprofil",c("Bitte wählen"=""))
    ),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("activity_quick_profile_refresh","Zuordnungsprofile lesen",class="btn-default"),
      shiny::actionButton("activity_quick_profile_load","Zuordnungsprofil laden",class="btn-default"),
      shiny::actionButton("activity_quick_profile_save","Aktuelle Zuordnung speichern",class="btn-default")
    ),
    shiny::uiOutput("profile_action_feedback"),
    shiny::uiOutput("activity_quick_profile_state"),
    shiny::div(class="pl-editor-actions",
      shiny::downloadButton("activity_quick_template","Quick-Export-Vorlage"),
      shiny::actionButton("activity_quick_inspect","Tolerante Datei prüfen",class="btn-default"),
      shiny::actionButton("activity_quick_prepare","Explizite Schlüsselzuordnung als ActivityDrafts vorbereiten",class="btn-default"),
      shiny::checkboxInput("activity_quick_confirm","Alle aktuell validierten bereiten Zeilen einmalig bestätigen",FALSE),
      shiny::actionButton("activity_quick_execute","Bereite Zeilen importieren",class="btn-primary")
    ),
    shiny::uiOutput("import_action_feedback"),
    shiny::uiOutput("activity_quick_state"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("activity_quick_rows")),
    shiny::tags$hr(),
    shiny::tags$h3(id='activity_pending_heading',tabindex='-1',"Offene ActivityDrafts bearbeiten"),
    shiny::p(class="pl-section-copy","Entwürfe mit fehlenden Angaben und blockierte Entwürfe bleiben lokal beim Eigentümer erhalten. Der Browser erhält nur flüchtige Auswahlkennungen; interne IDs, Pfade und Prüfabdrücke bleiben serverseitig."),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("activity_draft_refresh","Offene Entwürfe laden",class="btn-default"),
      shiny::selectInput("activity_draft_select","Offener Entwurf",c("Bitte wählen"="")),
      shiny::conditionalPanel("output.activity_draft_editable == 'yes'",
        shiny::selectInput("activity_draft_field","Feld",c("Bitte wählen"="")),
        shiny::selectInput("activity_draft_operation","Änderung",c("Wert setzen"="set_value","Explizit nicht anwendbar"="set_null","Als fehlend markieren"="remove")))
    ),
    shiny::uiOutput("activity_draft_value_ui"),
    shiny::uiOutput("activity_draft_valuation_ui"),
    shiny::div(class="pl-editor-actions",
      shiny::conditionalPanel("output.activity_draft_editable == 'yes'",
        shiny::actionButton("activity_draft_patch","Feld im Entwurf speichern",class="btn-default"),
        shiny::actionButton("activity_draft_revalidate","Entwurf erneut validieren",class="btn-default")),
      shiny::actionButton("activity_draft_resume","Unterbrochenen Entwurf fortsetzen",class="btn-default"),
      shiny::checkboxInput("activity_draft_confirm","Diesen validierten Entwurf einmalig bestätigen",FALSE),
      shiny::actionButton("activity_draft_commit","Validierten Entwurf übernehmen",class="btn-primary")
    ),
    shiny::uiOutput("draft_action_feedback"),
    shiny::uiOutput("activity_draft_batch_review"),
    shiny::uiOutput("activity_draft_state"),
    shiny::uiOutput("activity_draft_fee_resolution_ui"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("activity_draft_detail")),
    # Offene Entwuerfe in Worten (#420): gebuchte und abgeloeste stehen nicht mehr in der Liste; der Grund einer Blockade auf Knopfdruck.
    shiny::p(class="pl-field-hint","Die Liste zeigt nur offene Entwürfe. Offene Reste aus nicht gebuchten Vorschauen ändern am Bestand nichts."),
    shiny::div(class="pl-editor-actions",shiny::actionButton("activity_draft_reasons_run","Gründe der blockierten lesen",class="btn-default")),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("activity_draft_rows"))
  ),
  cash_import = portelyra_card(
    "Cash-Auszüge importieren",
    copy = "Kontoauszüge von Tagesgeld-, Bank- oder Börsen-Cash-Konten einlesen. Zinsen werden brutto als Ertrag und zugleich als Eingang gebucht, Steuern und Gebühren als Ausgang.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-cash-import", paste(
      "Bereits gebuchte Bewegungen werden erkannt. Belegt der Auszug Anfangs- und Endsaldo, wird der Zeitraum als vollständig abgeglichen erfasst.",
      "Es können mehrere Auszüge eines Kontos auf einmal gewählt werden; sie werden gemeinsam sortiert und geprüft. PDF-Auszüge werden lokal in Text umgewandelt; die Originaldatei bleibt unverändert.")),
    class = "pl-write-boundary",
    shiny::div(class="pl-form-grid",
      shiny::selectInput("cash_import_adapter","Quelle",choices=c("Bondora Go & Grow (xlsx oder CSV)"="bondora_go_grow_v1")),
      shiny::selectInput("cash_import_account","Cash-Konto",choices=c("Bitte Cash-Konten laden"="")),
      shiny::selectInput("cash_import_asset","Cash-Asset (Währung)",choices=c("Bitte Cash-Konten laden"="")),
      shiny::fileInput("cash_import_file","Auszüge auswählen (mehrere möglich)",accept=c(".xlsx",".csv",".pdf",".txt"),multiple=TRUE),
      # #462: nur die Brutto-Vorschlaege; die Bewegungen prueft der Import immer ueber den ganzen Auszug (Saldoprobe).
      # Leeres Datumsfeld: shiny warnt bei value = NA einmal je Feld; die Warnung stand beim Beenden im Startprotokoll (rc.412).
      suppressWarnings(shiny::dateInput("cash_import_gross_from","Brutto-Vorschläge berücksichtigen ab (leer: alle)",value=NA,format="dd.mm.yyyy",language="de"))
    ),
    shiny::uiOutput("cash_import_formats"),
    # Quelle „aus der Ablage“ nur mit dem Baustein Belege (#542); seit #583 steht ohne ihn der ganze Reiter „Import“ nicht da.
    data_module_only_v1("documents", data_statement_archive_source_ui_v1("cash_import", with_institution = FALSE)),
    shiny::checkboxInput("cash_import_text","Buchungstexte mitspeichern (optional, z. B. für spätere Unterscheidung von Herkünften)",FALSE),
    shiny::uiOutput("cash_import_state"),
    shiny::uiOutput("cash_import_action"),
    shiny::uiOutput("cash_import_balance_ui"),
    shiny::uiOutput("cash_import_gross_ui"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("cash_import_files")),
    shiny::tags$details(class="pl-disclosure",shiny::tags$summary("Bewegungen der Auszüge im Detail (neue zuerst, höchstens 500 Zeilen)"),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("cash_import_rows"))),
    shiny::tags$h4("Cash-Bewegungen je Konto"),
    shiny::div(class="pl-form-grid",shiny::selectInput("cash_movements_account","Konto",choices=c("Alle Cash-Konten"=""))),
    shiny::uiOutput("cash_movements_summary"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("cash_movements_table"))
  ),
  # Wertpapier-Belege der Institute (#446): Kaeufe, Verkaeufe, Dividenden aus PDF-Abrechnungen. Gebucht wird ueber den
  # Aktivitaeten-CSV-Import; diese Karte zeigt dessen Vorschau und bucht mit demselben Befehl.
  # Dieselbe Karte fuer Devisen (#449): Ueberschrift, Text und Leser folgen der Buchungsart. Krypto-Exporte (#454) liest ein eigener
  # Leser in der Buchungsart Non-Cash: alle Boersen und Wallets zugleich, damit Transfers ueber Dateigrenzen gepaart werden.
  securities_import = portelyra_card(
    shiny::tagList(desktop_mode_text_v1("input.import_kind == 'securities'", "Wertpapier-Belege importieren"),
      desktop_mode_text_v1("input.import_kind == 'crypto'", "Krypto-Exporte importieren"),
      desktop_mode_text_v1("input.import_kind == 'fx'", "Devisen-Belege importieren")),
    copy = shiny::tagList(desktop_mode_text_v1("input.import_kind == 'securities'", paste(
      "Abrechnungen eines Instituts einlesen: beliebig viele PDF-Dateien, CSV-Exporte (Smartbroker+, Trade Republic) oder ein ganzer Ordner samt Unterordnern. Käufe, Verkäufe und Dividenden werden gegen den Bestand geprüft; gebucht wird nur Neues, mit den Beträgen des Belegs.",
      "Depotüberträge, Splits und Steuerunterlagen bucht der Import nicht; sie erscheinen mit Grund in der Liste. Vorabpauschalen aus Belegen stehen in einer eigenen Tabelle und werden erst nach „Vorabpauschalen übernehmen“ eingetragen.")),
      desktop_mode_text_v1("input.import_kind == 'crypto'", paste(
      "Die CSV-Exporte der Börsen und Wallets gemeinsam wählen, am besten den ganzen Ordner: Käufe und Verkäufe gegen EUR und Transfers zwischen eigenen Konten.",
      "Transfers werden über Dateigrenzen gepaart; was ein Export nicht vollständig hergibt, bleibt offen und lässt sich im Editor vorbelegen. Rewards bucht die Importart „Rewards“.")),
      desktop_mode_text_v1("input.import_kind == 'fx'", paste(
      "Fremdwährungskonten einlesen – am einfachsten den ganzen Smartbroker+-Ordner: Devisenbelege werden Kauf und Verkauf des Devisen-Assets (Kurs = EUR-Gegenwert ÷ Betrag), Dividenden mit Gutschrift in Fremdwährung ein Zugang aus Ertrag.",
      "Die Kontoauszüge prüfen als Saldo-Anker, dass jede Bewegung belegt ist; die Dividende selbst bucht der Wertpapier-Leser."))),
    class = "pl-write-boundary",
    shiny::div(class="pl-form-grid",
      shiny::selectInput("securities_import_adapter","Institut",choices=desktop_securities_import_adapter_choices_v1()),
      shiny::fileInput("securities_import_files","Belege auswählen (mehrere möglich)",accept=c(".pdf",".txt",".csv"),multiple=TRUE),
      # Ordnerauswahl: der Browser liefert alle Dateien des Ordners samt Unterordnern; fremde Dateitypen bekommen einen Grund.
      htmltools::tagQuery(shiny::fileInput("securities_import_folder","… oder einen Ordner samt Unterordnern",multiple=TRUE,buttonLabel="Ordner wählen …"))$
        find("#securities_import_folder")$addAttrs(webkitdirectory=NA,directory=NA)$allTags()),
    # Leser lesen aus der Ablage (#434): dieselben Dateien wie dort hinterlegt, ohne Ordner ausserhalb.
    data_module_only_v1("documents", data_statement_archive_source_ui_v1("securities_import")),
    # Betrachteter Zeitraum (#462): Vorgabe ab dem letzten bestaetigten Import dieses Lesers; Aelteres wird nur gezaehlt.
    shiny::div(class="pl-form-grid",
      shiny::selectInput("securities_import_window","Betrachteter Zeitraum",choices=c("Ab dem letzten bestätigten Import dieses Lesers"="since_confirmed","Ab einem Datum"="chosen","Alle Zeiträume"="all")),
      shiny::conditionalPanel("input.securities_import_window == 'chosen'",suppressWarnings(shiny::dateInput("securities_import_from","Berücksichtigen ab",value=NA,format="dd.mm.yyyy",language="de"))),
      shiny::conditionalPanel("input.securities_import_window != 'all'",suppressWarnings(shiny::dateInput("securities_import_through","… bis (optional)",value=NA,format="dd.mm.yyyy",language="de")))),
    shiny::uiOutput("securities_import_adapter_info"),
    data_generic_statement_ui_v1(),
    shiny::uiOutput("securities_import_depots"),
    shiny::uiOutput("securities_import_reader_check"),
    # Umfang je Portfolio (#551): Vorgaenge einer nicht gewaehlten Klasse - dazunehmen oder ueberspringen, vor dem Buchen.
    shiny::uiOutput("securities_import_scope_ui"),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("securities_import_review","Belege prüfen",class="btn-default"),
      shiny::actionButton("securities_import_prepare","Neue Vorgänge vorbereiten",class="btn-default"),
      shiny::actionButton("securities_import_execute","Neue Vorgänge buchen",class="btn-primary")),
    shiny::uiOutput("securities_import_state"),
    shiny::uiOutput("securities_import_missing_ui"),
    shiny::uiOutput("securities_import_next_step"),
    shiny::uiOutput("securities_import_references_ui"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("securities_import_preview")),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("securities_import_rows")),
    shiny::uiOutput("securities_import_open_editor_ui"),
    shiny::uiOutput("securities_import_advance_ui"),
    shiny::uiOutput("securities_import_split_ui"),
    shiny::tags$details(class="pl-disclosure",shiny::tags$summary("Dateien ohne Buchung und ihr Grund"),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("securities_import_documents")))
  ),
  statements = portelyra_card(
    "Börsenauszüge importieren",
    copy = "Börse, Zeitraum und Datei wählen. Die Vorschau zeigt, welche Rewards neu sind und welche bereits gebucht sind.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-reward-import", paste(
      "Danach zwei Schritte: vorbereiten und prüfen, dann buchen. Die Datei darf die ganze Historie enthalten.")),
    class = "pl-write-boundary",
    # Zugeklappt, aber die Zahl steht in der Zeile: der Stand ist sichtbar, ohne
    # die Karte zu verlaengern (#422).
    shiny::tags$details(class="pl-disclosure",
      shiny::tags$summary(shiny::uiOutput("statement_resume_summary",inline=TRUE)),
      shiny::uiOutput("statement_resume_state")),
    shiny::div(class="pl-form-grid",
      shiny::selectInput("statement_exchange_adapter","Börse",choices=desktop_reward_adapter_choices_v1()),
      shiny::dateRangeInput("statement_exchange_period","Reward-Zeitraum (einschließlich)",start=as.Date("2000-01-01"),end=Sys.Date(),format="dd.mm.yyyy",separator=" bis "),
      shiny::fileInput("statement_exchange_file","CSV-Datei auswählen",accept=".csv",multiple=FALSE)
    ),
    # Wie die uebrigen Importe auch aus der Ablage (#520, Festlegung 31.10.2026): Alle Dateien der Boerse werden zusammen gelesen (rc.343).
    data_module_only_v1("documents", data_statement_archive_source_ui_v1("statement_exchange")),
    shiny::uiOutput("statement_exchange_reader_info"),
    shiny::uiOutput("statement_exchange_period_note"),
    shiny::uiOutput("statement_guided_state"),
    shiny::uiOutput("statement_reward_reader_check"),
    shiny::uiOutput("statement_guided_action"),
    shiny::uiOutput("statement_exchange_mapping_controls"),
    # Umfang je Portfolio (#551): Zuordnung auf ein Asset einer im Portfolio nicht gewaehlten Klasse - dazunehmen oder nicht zuordnen.
    shiny::uiOutput("statement_exchange_scope_ui"),
    shiny::uiOutput("statement_guided_special"),
    shiny::tags$details(id="statement-exchange-rows",class="pl-disclosure",
      shiny::tags$summary("Zeilen im Detail anzeigen"),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_exchange_tuples")),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_exchange_mapping_rows"))),
    # Auslöser der geführten Karte (#520): Sie klickt diese Knöpfe an. Die Einzelschritte dahinter entfallen bis auf eine aufklappbare Diagnose.
    shiny::div(id="statement_guided_triggers",style="display:none",`aria-hidden`="true",
      shiny::actionButton("statement_exchange_preview_run","Rewards anzeigen"),
      shiny::actionButton("statement_exchange_mapping_run","Zuordnung prüfen"),
      shiny::actionButton("statement_reward_collision_prepare","Zeitgleiche Rewards anzeigen"),
      shiny::checkboxInput("statement_reward_collision_confirm","Reihenfolge aus dem Auszug bestätigen",FALSE),
      shiny::actionButton("statement_reward_collision_apply","Reihenfolge übernehmen")),
    # Nur lesend: was die einzelnen Schritte zuletzt gemeldet haben, mit Codes. Erscheint nach einem Abbruch oder mit dem Schalter.
    data_when_needed_v1("statement_failed", shiny::tags$details(id="statement_diagnosis",class="pl-disclosure",
      shiny::tags$summary("Diagnose (nur bei Bedarf)"),
      shiny::p(class="pl-section-copy","Was die einzelnen Schritte zuletzt gemeldet haben, mit technischen Codes. Hier wird nichts geschrieben."),
      shiny::uiOutput("statement_exchange_status"),
      shiny::uiOutput("statement_reward_valuation_state"),
      shiny::uiOutput("statement_reward_market_batch_state"),
      shiny::uiOutput("statement_reward_validation_state"),
      shiny::uiOutput("statement_reward_collision_state"),
      shiny::uiOutput("statement_reward_canonical_state"),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_reward_canonical_rows")),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_reward_valuation_rows"))))
  ),
  # Tageshistorie (#473): je Tag, Konto und Asset fortgeschrieben; rechnet mit dem Tageskern des Stichtags-Snapshots.
  history = data_portfolio_history_card_ui_v1(),
  # Rechenstand (#422, rc.331): Hierher kamen die Knoepfe aus "Manuell"; "State lesen" und "Betroffene Welten aktualisieren"
  # waren dieselben Schritte wie "pruefen" und "nachrechnen" hier. Komplett neu rechnen und gegenpruefen bleiben Fachleuten.
  completion = portelyra_card(
    "Rechenstand der Bestände (FIFO)",
    copy = paste("Nach jeder Buchung, jedem Import und jeder Korrektur rechnet Portelyra Bestand, Einstandswert und realisierte GuV",
                 "der betroffenen Assets selbst nach. Hier sehen Sie, ob diese Rechnung auf dem Stand der Buchungen ist."),
    note = portelyra_note_v1(title = "So lesen Sie den Rechenstand", id = "data-portfolio-update", shiny::tags$ul(
      shiny::tags$li("„Aktuell“: Alle Buchungen sind eingerechnet."),
      shiny::tags$li("„Liegt zurück“: Seit der letzten Rechnung wurde gebucht oder korrigiert, etwa nach einem abgebrochenen Vorgang. „Nachrechnen“ rechnet nur die betroffenen Assets neu; alles andere bleibt, wie es ist."),
      shiny::tags$li("„Bewertung belastbar“: Bestand, Kurse und Wechselkurse reichen für eine Bewertung. Fehlt etwas, nennt die Zeile, woran es liegt."),
      shiny::tags$li("Prüfen und Nachrechnen rufen keinen Kursanbieter ab und ändern keine Buchung. Kurse, Snapshot und Abschluss kommen mit „Alles aktualisieren“."))),
    class = "pl-write-boundary",
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("portfolio_completion_check","Rechenstand prüfen",class="btn-default"),
      shiny::checkboxInput("portfolio_completion_confirm","Betroffene Assets jetzt nachrechnen",FALSE),
      shiny::actionButton("portfolio_completion_update","Nachrechnen",class="btn-primary")
    ),
    shiny::uiOutput("portfolio_completion_status"),
    shiny::uiOutput("portfolio_readiness_panel"),
    data_expert_only_v1(shiny::tags$details(class="pl-disclosure", id="data-realized-state-expert",
      shiny::tags$summary("Für Fachleute · komplett neu rechnen und gegenprüfen"),
      shiny::p(class="pl-section-copy", paste(
        "„Komplett neu rechnen“ rechnet alle Assets aus allen Buchungen neu, statt nur die betroffenen fortzuschreiben.",
        "„Fortschreibung gegenprüfen“ rechnet zur Kontrolle komplett neu und vergleicht das Ergebnis mit dem fortgeschriebenen Stand; es ändert nichts.",
        "Beides braucht es nur, wenn ein Ergebnis zweifelhaft ist.")),
      shiny::div(class="pl-editor-actions",
        shiny::actionButton("realized_state_full","Komplett neu rechnen",class="btn-default"),
        shiny::actionButton("realized_state_verify","Fortschreibung gegenprüfen",class="btn-default")),
      shiny::uiOutput("realized_state_status"),
      shiny::tags$h4("Bereitschaft je Bereich"),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("realized_state_dimensions")),
      shiny::tags$h4("Rechenstand je Asset · die unten ausgewählten, sonst alle"),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("realized_state_positions")))),
    shiny::selectizeInput("portfolio_completion_assets","Assets ansehen",choices=character(),multiple=TRUE,
      options=list(placeholder="Ein oder mehrere Assets auswählen …",plugins=list("remove_button"),closeAfterSelect=FALSE,maxOptions=5000)),
    shiny::tags$h3("Bestand der ausgewählten Assets"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("portfolio_completion_positions")),
    shiny::tags$h3("Buchungen der ausgewählten Assets · neueste zuerst"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("portfolio_completion_history")),
    shiny::tags$hr(),
    # Bis wann sind die Transaktionen je Asset und Konto abgeglichen? Das Datum der
    # letzten Buchung sagt das nicht: Hat ein Asset lange keine Buchung, ist nicht
    # zu erkennen, ob nichts passiert
    # ist oder ob niemand nachgesehen hat (#423).
    shiny::tags$h3("Pflegestand je Asset und Konto"),
    portelyra_note_v1(title = "So lesen Sie den Pflegestand", id = "data-maintenance", shiny::p("Zwei Spuren je Paar: Rewards pflegt der Reward-Import, die übrigen Transaktionen erklären Sie. Wirksam ist der ältere der beiden Stände.",
      " Die Liste ist nach Konto gruppiert, damit der Durchgang Depot für Depot geht.")),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("asset_maintenance_read","Pflegestand lesen",class="btn-default"),
      shiny::span(class="pl-field-hint","Liest nur. Kein Kursabruf, keine Buchung.")),
    shiny::uiOutput("asset_maintenance_state"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("asset_maintenance_table")),
    # Erklaeren und Sammelsetzung (#423, Schritt 2). Der eigentliche Nutzen liegt
    # im Haekchen: An einem Tag ohne Trades erklaert ein Vorgang den ganzen
    # Non-Cash-Bestand als geprueft. Ohne das muessten alle
    # Positionen einzeln bestaetigt werden, und das geschaehe nicht.
    shiny::tags$h4("Pflegestand erklären"),
    shiny::p(class="pl-section-copy",
      "Erklärt wird ausschließlich die Spur der übrigen Transaktionen. Die Reward-Spur setzt der Reward-Import; keine Quelle beschreibt das Feld der anderen.",
      " Eine Erklärung ist eine Zusicherung: bis zu diesem Tag beim Broker geprüft, alle Bewegungen erfasst – auch wenn es keine gab."),
    shiny::div(class="pl-form-grid",
      desktop_product_empty_date_input_v1("asset_maintenance_through","Geprüft bis einschließlich"),
      shiny::radioButtons("asset_maintenance_scope","Umfang",
        c("Alle Paare ohne Bewegung seit ihrem letzten Stand"="unmoved",
          "Nur die unten ausgewählten Paare"="selected",
          "Zusicherung der ausgewählten Paare zurücknehmen"="retract"),
        selected="unmoved"),
      shiny::conditionalPanel("input.asset_maintenance_scope != 'unmoved'",
        shiny::selectizeInput("asset_maintenance_pairs","Asset-Konto-Paare",choices=NULL,multiple=TRUE,
          options=list(placeholder="Paare wählen")))),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("asset_maintenance_prepare","Erklärung prüfen",class="btn-default"),
      shiny::checkboxInput("asset_maintenance_confirm","Vorschau geprüft – genau diese Erklärung einmalig bestätigen",FALSE),
      shiny::actionButton("asset_maintenance_apply","Bestätigt erklären",class="btn-primary")),
    shiny::uiOutput("asset_maintenance_preview_state"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("asset_maintenance_preview_table")),
    shiny::uiOutput("asset_maintenance_action_feedback"),
    data_expert_only_v1(shiny::tags$details(class="pl-disclosure",
      shiny::tags$summary("Pflegeläufe · wann wurde was erklärt"),
      shiny::p(class="pl-section-copy",
        "Ein Lauf je Vorgang. Daraus folgt, wie alt der Pflegestand über den ganzen Bestand ist. Läufe bleiben erhalten, bis Du sie ausdrücklich entfernst."),
      shiny::div(class="pl-editor-actions",
        shiny::actionButton("asset_maintenance_runs_read","Pflegeläufe lesen",class="btn-default")),
      shiny::uiOutput("asset_maintenance_runs_state"),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("asset_maintenance_runs_table"))))
  ),
  setup = portelyra_card(
    "Portelyra erstmalig einrichten",
    copy = paste("Nur einmal bei einer neuen, leeren Installation nötig.","Weitere Portfolios werden in den Einstellungen unter „Portfolio“ → „Portfolios“ angelegt und erfordern keine erneute Einrichtung. Der App-Start schreibt nichts."),
    class = "pl-write-boundary",
    shiny::div(
      class = "pl-editor-actions",
      shiny::checkboxInput("confirm_initialize", "Leere Datenablage genau einmal einrichten", FALSE),
      shiny::actionButton("initialize_data_space", "Bestätigt einrichten", class = "btn-primary")
    )
  ),
  exchange = portelyra_card(
    "Portfolio-Daten austauschen",
    copy = "Transparenter lokaler Ordner: Exporte werden nur neu angelegt, der Eingangsordner arbeitet verlustfrei und redundant, ohne verstecktes Schreiben in den Bestand.",
    class = "pl-write-boundary",
    data_portfolio_csv_exchange_ui_v1()
  ),
  # Ohne eigene Karte: Der Aufklapper in den Stammdaten traegt schon den Titel (doppelt, Befund 23.10.2026).
  workspace = shiny::div(class = "pl-readonly",
    shiny::p(class = "pl-section-copy", "Alle angelegten Stammdaten auf einen Blick: Bezeichnungen, Typen, Währungen, Datumswerte und Zähler."),
    shiny::uiOutput("workspace_status"),
    shiny::uiOutput("workspace_counts"),
    shiny::tags$h3("Portfolios"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("workspace_portfolios")),
    shiny::tags$h3("Konten"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("workspace_accounts")),
    shiny::tags$h3("Assets"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("workspace_assets")),
    data_expert_only_v1(shiny::tags$details(class = "pl-disclosure", shiny::tags$summary("Archiv anzeigen"),
      shiny::p(class = "pl-section-copy", "Archivierte Stammdaten bleiben aus Gründen der Nachvollziehbarkeit gespeichert, erscheinen aber in keiner Auswahl mehr."),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("workspace_archive"))))
  ),
  catalog = portelyra_card(
    "Sonderfälle · Archivieren und Sammelanlage per CSV",
    copy = "Anlegen und Umbenennen von Portfolios, Konten und Assets erfolgt direkt im Stammdaten-Tab. Hier bleiben nur Archivieren und die Sammelanlage per CSV.",
    class = "pl-write-boundary",
    shiny::actionButton("catalog_refresh", "Auswahl lesen", class = "btn-default"),
    shiny::uiOutput("catalog_state"),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("catalog_entity_type", "Bereich", c("Portfolio" = "portfolio", "Konto" = "account", "Asset" = "asset")),
      shiny::selectInput("catalog_entity_ref", "Zu archivierender Datensatz", c("Bitte wählen" = ""))
    ),
    shiny::p(class = "pl-field-hint", "Archivieren entfernt den Datensatz aus der Auswahl; bestehende Buchungen bleiben unverändert."),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("catalog_prepare", "Archivierung prüfen", class = "btn-default"),
      shiny::checkboxInput("catalog_confirm", "Genau diese Archivierung einmalig bestätigen", FALSE),
      shiny::actionButton("catalog_execute", "Bestätigt archivieren", class = "btn-primary")
    ),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("catalog_preview")),
    shiny::tags$hr(),
    shiny::tags$h3("Sammelanlage per CSV · nur Neuanlage"),
    shiny::p(class = "pl-section-copy", "Die CSV verwendet ausdrücklich vom Nutzer vergebene row_ref-Werte. Bestehende Portfolios werden ausschließlich über die angezeigten Austauschkennungen gebunden; Namen erzeugen keine Identität."),
    shiny::div(class = "pl-editor-actions",
      shiny::downloadButton("catalog_csv_template", "Leere desktop-catalog.csv"),
      shiny::fileInput("catalog_csv_file", "desktop-catalog.csv auswählen", accept = ".csv", multiple = FALSE),
      shiny::actionButton("catalog_csv_prepare", "CSV-Vorschau prüfen", class = "btn-default"),
      shiny::actionButton("catalog_csv_resume", "Unterbrochenen CSV-Import prüfen", class = "btn-default"),
      shiny::checkboxInput("catalog_csv_confirm", "Genau diesen CSV-Plan einmalig bestätigen", FALSE),
      shiny::actionButton("catalog_csv_execute", "Bestätigten CSV-Plan ausführen", class = "btn-primary")
    ),
    shiny::tags$h3("Explizite Portfolio-Refs"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("catalog_csv_references")),
    shiny::tags$h3("CSV-Plan"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("catalog_csv_preview"))
  ),
  kraken_lab = portelyra_card(
    "Kraken-Ledger Zuordnung synthetisch erproben",
    copy = paste(
      "Ausschließlich erfundene Zeilen: exakte Spaltenrollen, type-/subtype-/aclass-Routen, browserlokale Katalogauswahl,",
      "manuelle Reward-Bewertung und vollständige Abstimmung. Das Profil ist noch nicht an echten Exporten geprüft."
    ),
    class = "pl-readonly",
    shiny::div(
      class="pl-form-grid",
      shiny::selectInput(
        "statement_workspace_scenario", "Erfundenes Bewertungs-Szenario",
        choices=c(
          "Bewertungsbasis fehlt sichtbar"="basis_missing",
          "Exakter manueller Fiat-Gesamtwert"="manual_fiat_total",
          "Exakter manueller Stückkurs"="manual_unit_price"
        )
      )
    ),
    shiny::div(
      class="pl-editor-actions",
      shiny::actionButton("statement_workspace_run", "Erfundenes Kraken-Ledger prüfen", class="btn-primary")
    ),
    shiny::uiOutput("statement_workspace_status"),
    shiny::uiOutput("statement_workspace_profile"),
    shiny::tags$h3("Explizite Spaltenrollen"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_workspace_columns")),
    shiny::tags$h3("Explizite type-/subtype-/aclass-Routen"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_workspace_routes")),
    shiny::tags$h3("Browserlokale Katalogzuordnung"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_workspace_catalog")),
    shiny::uiOutput("statement_workspace_valuation"),
    shiny::tags$h3("Vollständige Zeilenbilanz"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_workspace_counts")),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_workspace_rows")),
    shiny::p(
      class="pl-section-copy",
      "Keine private Dateiauswahl · kein Übernehmen der Zuordnung · keine Bestätigung von Katalog, Buchungsentwurf, Korrektur oder Cash · kein Kursabruf · keine Aktivierung"
    )
  ),
  mapping_lab = portelyra_card(
    "Allgemeine Zuordnung von Auszügen und spätere Bewertung",
    copy = paste(
      "Anbieterneutrale Zielarchitektur für alle Auszugsadapter:",
      "Jedes Quell-Asset × Quellkonto × Ereignis wird einem vorhandenen Asset × Konto zugeordnet oder sichtbar zurückgestellt."
    ),
    class = "pl-readonly",
    shiny::div(class="pl-form-grid",
      shiny::selectInput("statement_mapping_scenario","Erfundenes Bewertungs-Szenario",choices=c(
        "CSV enthält keine Bewertung · später manuell"="source_missing",
        "CSV enthält exakten Stückpreis"="source_unit_price",
        "CSV enthält exakten Fiat-Gesamtwert"="source_fiat_total",
        "CSV-Währung benötigt separate Umrechnung"="foreign_currency"
      ))
    ),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("statement_mapping_run","Allgemeine Übergabe der Zuordnung erproben",class="btn-primary")
    ),
    shiny::uiOutput("statement_mapping_status"),
    shiny::tags$h3("Inventar aller Quellkombinationen"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_mapping_tuples")),
    shiny::tags$h3("Vollständige Zeilendisposition"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_mapping_rows")),
    shiny::p(class="pl-section-copy",paste(
      "Diese Ausbaustufe der Architektur verwendet nur erfundene Zeilen und schreibt keine Entwürfe.",
      "Normale Kraken-/Coinbase-/weitere Adapter, private Datei-Auswahl und Aktivierung bleiben separat gesperrt."
    ))
  ),
  cash = portelyra_card(
    "Cash-Abdeckung und Zinserträge getrennt führen",
    copy = "Cash wird ausdrücklich je Konto und Zeitraum als nicht gepflegt, nur Erträge, teilweise oder vollständig abgestimmt erklärt.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-cash-booking", paste(
      "Zinsertrag und Cashbewegung bleiben getrennt; fehlendes Cash ist nie null.")),
    class = "pl-write-boundary",
    shiny::actionButton("cash_refresh", "Cash-Auswahl und Read Model aktualisieren", class="btn-default"),
    shiny::uiOutput("cash_state"),
    # Eine Cash-Buchung aus Konto, Datum, Betrag und Art. Der Weg ueber die zwanzig Felder verlangte dafuer
    # Ortszeit, Zeitzone, UTC-Zeitstempel und einen von Hand beschafften SHA-256.
    # Die Felder darunter bleiben fuer Sonderfaelle hinter "Erweitert" (#419).
    # Kleinstbestaende auf geschlossenen Konten (#534): fuellt das Formular darunter vor.
    data_small_holdings_card_ui_v1(),
    shiny::tags$h3("Cash-Buchung eintragen"),
    shiny::div(class="pl-form-grid",
      shiny::selectInput("cash_simple_account","Konto",c("wird geladen …"="")),
      desktop_product_empty_date_input_v1("cash_simple_date","Datum"),
      shiny::selectInput("cash_simple_kind","Art",c("Zugang"="deposit","Abgang"="withdrawal","Zinsgutschrift"="interest")),
      shiny::textInput("cash_simple_amount","Betrag","",placeholder="z. B. 1240,28")),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("cash_simple_prepare","Buchung prüfen",class="btn-default"),
      shiny::checkboxInput("cash_simple_confirm","Vorschau geprüft – genau diese Buchung einmalig bestätigen",FALSE),
      shiny::actionButton("cash_simple_execute","Buchen",class="btn-primary")),
    shiny::uiOutput("cash_simple_state"),
    # Ein Saldo, der online geprueft ist, liess sich nicht festhalten: Exporte ohne
    # Saldospalte bleiben `partial`, und nachtraeglich fuehrte kein Weg auf
    # abgestimmt (#417). Der Pruef-Saldo hebt den Zeitraum an; der Nachweis ist
    # eine Datei, eine Sichtung oder - wo gar kein Saldo zu bekommen ist - eine
    # ausdrueckliche Erklaerung ohne Pruefung.
    shiny::tags$h3(id="cash_check_heading","Saldo prüfen · Abdeckung abstimmen"),
    shiny::div(class="pl-form-grid",
      shiny::selectInput("cash_check_account","Konto",c("wird geladen …"="")),
      desktop_product_empty_date_input_v1("cash_check_date","Stand am"),
      shiny::radioButtons("cash_check_evidence","Nachweis",
        c("Online gesichtet"="owner_sighted","Beleg-Datei"="document",
          "Kein Saldo zu bekommen – Vollständigkeit erklären"="owner_asserted_without_balance"),selected="owner_sighted"),
      shiny::conditionalPanel("input.cash_check_evidence != 'owner_asserted_without_balance'",
        shiny::textInput("cash_check_balance","Saldo an diesem Tag","",placeholder="z. B. 1250,00")),
      # Die Datei bleibt, wo sie ist: gelesen wird sie nur, um ihren SHA-256 zu
      # bilden - wie beim Statement-Import. Niemand tippt 64 Zeichen ab.
      shiny::conditionalPanel("input.cash_check_evidence == 'document'",
        shiny::fileInput("cash_evidence_file","Beleg wählen",multiple=FALSE))),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("cash_check_prepare","Saldo prüfen",class="btn-default"),
      shiny::checkboxInput("cash_check_confirm","Vorschau geprüft – genau diese Abstimmung einmalig bestätigen",FALSE),
      shiny::actionButton("cash_check_execute","Abstimmung festhalten",class="btn-primary")),
    shiny::uiOutput("cash_check_state"),
    shiny::tags$h3("Nachweise je Konto · bis wann ist der Saldo belegt"),
    shiny::uiOutput("cash_evidence_state"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("cash_evidence_table")),
    data_expert_only_v1(shiny::tags$details(class="pl-disclosure pl-lazy",id="cash_advanced",
    shiny::tags$summary("Erweitert · Zeiträume, Historie, alle Cash-Kommandos und Korrektur"),
    shiny::tags$h3("Zeiträume der Cash-Abdeckung"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("cash_periods")),
    shiny::tags$h3("Cash-Historie · neueste zuerst"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("cash_history")),
    shiny::tags$h3("Ertragshistorie · getrennt"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("cash_income")),
    shiny::tags$h3("Unveränderliche Belege · neueste zuerst"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("cash_receipts")),
    # Jedes Feld erscheint nur, wenn die gewaehlte Aktion es liest. Die Bedingung
    # ist aus der Relevanzliste des Editors abgeleitet, nicht von Hand gepflegt
    # (#422).
    shiny::div(class="pl-form-grid",
      shiny::selectInput("cash_action","Aktion",c("Abdeckungszeitraum erklären"="declare_coverage","Cash-Ereignis"="record_cash_event","Zinsertrag"="record_interest_income","Abstimmung"="record_reconciliation","Bestehende Fakten korrigieren"="correct","Bestehende Fakten ersetzen"="supersede","Bestehende Fakten stornieren"="void")),
      desktop_product_cash_field_v1("revision_predecessor_refs",shiny::selectizeInput("cash_predecessors","Zu korrigierende Cash-Datensätze",c("Bitte zunächst aktualisieren"=""),multiple=TRUE)),
      desktop_product_cash_field_v1("portfolio_ref",shiny::selectInput("cash_portfolio","Portfolio",c("Bitte wählen"=""))),
      desktop_product_cash_field_v1("account_ref",shiny::selectInput("cash_account","Cash-/Bank-/Verwahrkonto",c("Bitte wählen"=""))),
      desktop_product_cash_field_v1("cash_asset_ref",shiny::selectInput("cash_asset","Cash-Asset",c("Bitte wählen"=""))),
      desktop_product_cash_field_v1("related_account_ref",shiny::selectInput("cash_related_account","Zielkonto bei internem Transfer",c("Nicht anwendbar"=""))),
      desktop_product_cash_field_v1("coverage_mode",shiny::selectInput("cash_coverage_mode","Abdeckungsart",c("Nicht gepflegt"="not_tracked","Nur Erträge"="income_only","Teilweise"="partial","Vollständig abgestimmt"="complete_reconciled"))),
      desktop_product_cash_field_v1("effective_from",desktop_product_empty_date_input_v1("cash_effective_from","Gültig ab")),
      desktop_product_cash_field_v1("effective_to",desktop_product_empty_date_input_v1("cash_effective_to","Gültig bis (optional)")),
      desktop_product_cash_field_v1("event_type",shiny::selectInput("cash_event_type","Cash-Ereignis",c("Anfangssaldo"="opening_balance","Zugang"="deposit","Abgang"="withdrawal","Interner Transfer"="transfer"))),
      desktop_product_cash_field_v1("local_date",desktop_product_empty_date_input_v1("cash_local_date","Ereignisdatum")),
      desktop_product_cash_field_v1("local_time",shiny::textInput("cash_local_time","Lokale Uhrzeit (HH:MM:SS)","")),
      desktop_product_cash_field_v1("time_zone",shiny::textInput("cash_time_zone","IANA-Zeitzone","Europe/Berlin")),
      desktop_product_cash_field_v1("effective_at_utc",shiny::textInput("cash_effective_utc","Ereigniszeit UTC · leer = aus Datum, Uhrzeit und Zeitzone","")),
      desktop_product_cash_field_v1("amount_decimal",shiny::textInput("cash_amount","Exakter Cash-Betrag / Anfangssaldo","")),
      desktop_product_cash_field_v1("flow_classification",shiny::selectInput("cash_flow_classification","Art der Bewegung",c("Nicht anwendbar"="not_applicable","Unklassifiziert"="unclassified","Externe Einzahlung"="external_contribution","Externe Auszahlung"="external_withdrawal","Intern nicht verknüpft"="internal_unlinked","Abrechnung eines Wertpapiergeschäfts"="investment_settlement","Ertragseingang"="income_receipt","Zahlung von Gebühr oder Steuer"="fee_or_tax_payment"))),
      desktop_product_cash_field_v1("gross_income_decimal",shiny::textInput("cash_interest_amount","Exakter Zinsertrag","")),
      desktop_product_cash_field_v1("linked_cash_event_ref",shiny::selectInput("cash_linked_event","Verknüpfung mit einer Cash-Bewegung (optional)",c("Nicht verknüpfen"=""))),
      desktop_product_cash_field_v1("as_of_date",desktop_product_empty_date_input_v1("cash_as_of_date","Abstimmungsdatum")),
      desktop_product_cash_field_v1("observed_balance_decimal",shiny::textInput("cash_observed_balance","Beobachteter exakter Saldo","")),
      desktop_product_cash_field_v1("evidence_fingerprint",shiny::textInput("cash_evidence_fingerprint","SHA-256 des Abstimmungsnachweises · ohne Beleg: Karte „Saldo prüfen“",""))
    ),
    shiny::uiOutput("cash_action_fields"),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("cash_prepare","Vorschau der Cash-Abdeckung prüfen",class="btn-default"),
      shiny::checkboxInput("cash_confirm","Genau diesen Vorgang zur Cash-Abdeckung einmalig bestätigen",FALSE),
      shiny::actionButton("cash_execute","Bestätigt schreiben",class="btn-primary")
    ),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("cash_preview")))),
    # Aus "Erweitert" geloest (#492, Festlegung 23.10.2026): erscheint von selbst, sobald ein Versuch offen ist.
    data_when_needed_v1("cash_recovery", shiny::tags$details(class="pl-disclosure",open=NA,shiny::tags$summary("Mehrdeutige Schreibversuche sicher abgleichen"),
    shiny::selectInput("cash_recovery_candidate","Kandidat für die Wiederaufnahme",c("Keine Kandidaten"="")),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton("cash_recovery_prepare","Vorschau der Wiederaufnahme prüfen",class="btn-default"),
      shiny::checkboxInput("cash_recovery_confirm","Genau diesen Wiederaufnahmeplan einmalig bestätigen",FALSE),
      shiny::actionButton("cash_recovery_execute","Bestätigte Wiederaufnahme ausführen",class="btn-primary")
    ),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("cash_recovery_preview"))
    ))
  ),
  transactions = portelyra_card(
    "Bestehende gekoppelte Transaktionen verwalten",
    copy = "Historische gekoppelte Fakten bleiben unter ihrer ursprünglichen Semantik korrigierbar oder stornierbar; neue Buchungen werden hier nicht als Cash-gekoppelte Transaktion angelegt.",
    class = "pl-write-boundary",
    shiny::actionButton("transaction_refresh", "Auswahl aktualisieren", class = "btn-default"),
    shiny::uiOutput("transaction_state"),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("transaction_action", "Aktion", c("Korrigieren" = "correct", "Stornieren" = "void"), selected = "correct"),
      shiny::selectInput("transaction_current", "Aktuelle Transaktion", c("Bitte wählen" = "")),
      shiny::selectInput("transaction_profile", "Profil", c("Kauf" = "buy", "Verkauf" = "sell", "Einzahlung" = "deposit", "Auszahlung" = "withdrawal", "Interner Transfer" = "internal_transfer")),
      shiny::selectInput("transaction_portfolio", "Portfolio", c("Bitte wählen" = "")),
      shiny::textInput("transaction_effective", "Zeitpunkt UTC", ""), shiny::textInput("transaction_date", "Lokales Datum", ""),
      shiny::selectInput("transaction_account", "Asset-Konto", c("Bitte wählen" = "")), shiny::selectInput("transaction_asset", "Asset", c("Bitte wählen" = "")),
      shiny::selectInput("transaction_cash_account", "Cash-Konto", c("Bitte wählen" = "")), shiny::selectInput("transaction_cash_asset", "Cash-Asset", c("Bitte wählen" = "")),
      shiny::selectInput("transaction_counterparty", "Externes Gegenkonto", c("Bitte wählen" = "")), shiny::selectInput("transaction_destination", "Zielkonto", c("Bitte wählen" = "")),
      shiny::textInput("transaction_quantity", "Menge", ""), shiny::textInput("transaction_price", "Stückpreis", ""), shiny::textInput("transaction_amount", "Betrag / gebuchter Bruttobetrag (bei Kauf/Verkauf optional)", ""),
      shiny::textInput("transaction_fee", "Gebühr (optional)", ""), shiny::textInput("transaction_tax", "Aufgezeichnete Steuer (optional)", ""), shiny::textInput("transaction_memo", "Notiz (optional)", "")
    ),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("transaction_load", "Aktuelle Werte laden", class = "btn-default"),
      shiny::actionButton("transaction_prepare", "Vorschau prüfen", class = "btn-default"),
      shiny::checkboxInput("transaction_confirm", "Genau diese Vorschau einmalig bestätigen", FALSE),
      shiny::actionButton("transaction_execute", "Bestätigt schreiben", class = "btn-primary")
    ),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("transaction_preview"))
  ),
  legacy = portelyra_card(
    "Prüfung des Altbestands je Asset und getrennte Übernahme in den Bestand",
    copy = paste(
      "Die Quelle ist eine serverseitig gebundene, nur lesende Berechtigung. Browserwerte enthalten keine Pfade, Kontext- oder kanonischen IDs.",
      "Probe und Übernahme in den Bestand haben getrennte Vorschauen und Einmalbestätigungen. Eine Buchung erzeugt keine automatische Cash-Gegenbuchung."
    ),
    class = "pl-write-boundary pl-per-asset-legacy-review",
    data_per_asset_legacy_review_module_ui_v1("per_asset_review")
  ),
  run = portelyra_card(
    "Abschluss",
    shiny::tags$span(id="desktop-run-center"),
    copy = paste("Ein Plan bindet Stammdaten → FIFO/GuV → Steuer → Gruppierung → manuelle Kurse/FX oder abgeschlossene EUR-Nachweise → Bewertung → Handels- und Marktanalyse → atomare Veröffentlichung.",
                 "Ein vollständiger Neuaufbau ist vor dem ersten fortschreibenden Abschluss Pflicht; ein fehlender Nachweis bleibt sichtbar als „teilweise“ oder „blockiert“."),
    class = "pl-write-boundary",
    shiny::actionButton("run_catalog_refresh", "Abschluss-Eingaben lesen", class = "btn-default"),
    shiny::uiOutput("run_state"),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("run_portfolio", "Portfolio", c("Bitte wählen" = "")),
      shiny::selectInput("run_mode", "Modus", c("Vollständiger Neuaufbau" = "full", "Fortschreiben (gleiches Ergebnis wie Neuaufbau)" = "incremental")),
      # Ein Textfeld fuer ein Datum verlagert die Formatpruefung auf den Nutzer,
      # und der Fehlercode nannte das Feld nicht. Der Cutoff folgt aus dem
      # Bewertungsdatum (Tagesgrenze danach) und wird mitgezogen, bleibt aber
      # aenderbar (Festlegung 28.09.2026).
      shiny::dateInput("run_as_of_date", "Bewertungsdatum", value = Sys.Date() - 1L,
        min = as.Date("1900-01-01"), max = as.Date("9999-12-31"),
        format = "dd.mm.yyyy", language = "de", weekstart = 1L),
      shiny::textInput("run_cutoff", "Stichzeitpunkt (UTC)", ""),
      shiny::selectInput("run_tax_mode", "Steuermodul", c("Nicht auswählen" = "disabled", "Deutsches Referenzmodell v2 explizit" = "de_reference_v2", "Deutsches Referenzmodell v1 kompatibel" = "de_reference_v1")),
      shiny::textInput("run_capital_rate", "Kapitalertragsteuersatz % (optional)", ""),
      shiny::textInput("run_personal_rate", "Persönlicher Satz % (optional)", ""),
      shiny::textInput("run_soli_rate", "Solidaritätszuschlag % (optional)", ""),
      shiny::selectInput("run_church_applicable", "Kirchensteuer anwendbar (v2, ausdrücklich)", c("Bitte wählen" = "", "Anwendbar" = "applicable", "Nicht anwendbar" = "not_applicable")),
      shiny::textInput("run_church_rate", "Kirchensteuersatz % (nur bei anwendbar)", "")
    ),
    # Die Liquidationsgebuehr je Asset zu tippen ist bei vielen Assets kein Weg.
    # Der Lauf waehlt eine Quelle fuer alle; eine Asset-Karte darf sie
    # ueberschreiben, wie bei der Steuer (Festlegung 28.09.2026, #367).
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("run_fee_source", "Liquidationsgebühr · Quelle für alle Assets", c(
        "Aus bisherigen Transaktionen abgeleitet (empfohlen)" = "derived_from_transactions",
        "Fester Betrag je Trade" = "fixed_per_trade",
        "Fester Prozentsatz vom Umsatz" = "percentage_of_turnover")),
      shiny::textInput("run_fee_fixed", "Fester Betrag je Trade in EUR", "", placeholder = "nur bei fester Gebühr"),
      shiny::textInput("run_fee_percentage", "Fester Prozentsatz vom Umsatz", "", placeholder = "nur bei Prozentsatz")
    ),
    shiny::uiOutput("run_fee_hint"),
    shiny::checkboxInput("run_completed_market","Abgeschlossene EUR-Bewertung als exakten Marktwertteil einbinden",FALSE),
    shiny::conditionalPanel("input.run_completed_market",
      shiny::actionButton("run_valuation_read","Abgeschlossene Bewertungen lesen"),
      shiny::selectInput("run_valuation_ref","Bewertung für diesen Abschluss",choices=NULL),
      shiny::p("Manuelle Preise und FX-Raten leer lassen. Stichzeitpunkt: Bewertungsdatum 23:59:59Z. Marktwert ohne Cash, Steuern oder Netto-Liquidation; kein Gesamtabschluss.")),
    shiny::uiOutput("run_market_source"),
    # Eine Karte mit Suche statt einer je Asset (#422, Festlegung 17.10.2026, Variante 1).
    portelyra_card("Manueller Nachweis je Asset", copy = paste("Kurs und Kurswährung kommen aus dem Bewertungsstand; diese Felder greifen nur, wo er",
        "für den Stichtag nichts trägt. Asset suchen, Werte setzen – sie bleiben beim Wechsel zum nächsten Asset stehen und gelten für den",
        "nächsten Abschlussplan. Leere Kurs- und FX-Werte bleiben sichtbar „nicht verfügbar“."),
      shiny::selectizeInput("run_evidence_asset", "Asset", choices = character(), options = list(placeholder = "Asset suchen …")),
      shiny::conditionalPanel("input.run_evidence_asset && input.run_evidence_asset.length > 0",
        shiny::div(class = "pl-form-grid",
          shiny::textInput("run_ev_listing", "Notierungscode (explizit)", ""),
          shiny::textInput("run_ev_currency", "Kurswährung", ""),
          shiny::textInput("run_ev_close", "Schlusskurs", ""), shiny::textInput("run_ev_observed", "Kurszeitpunkt (UTC)", ""),
          shiny::selectInput("run_ev_tax", "Steuerliche Einordnung", c("Nicht konfiguriert" = "not_configured", "Aktie" = "de_equity_share", "Kapitalinstrument" = "de_capital_instrument", "Cash-Zins" = "de_cash_interest", "Fonds" = "de_fund", "Privates Veräußerungsasset" = "de_private_disposal_asset", "Sonstiges Einkommen" = "de_other_income_asset")),
          shiny::textInput("run_ev_partial", "Teilfreistellung % (optional)", ""),
          shiny::textInput("run_ev_fixed_fee", "Liquidationsgebühr fix · leer = Laufvorgabe", ""),
          shiny::textInput("run_ev_percentage_fee", "Liquidationsgebühr % · leer = Laufvorgabe", ""),
          shiny::selectInput("run_ev_fx_direction", "Explizite FX-Route", c("Keine" = "none", "Direkt" = "direct", "Invers" = "inverse")),
          shiny::textInput("run_ev_fx_base", "FX Basiswährung", ""), shiny::textInput("run_ev_fx_quote", "FX Quotierungswährung", ""),
          shiny::textInput("run_ev_fx_rate", "Devisenkurs", ""), shiny::textInput("run_ev_fx_observed", "Devisenkurszeitpunkt (UTC)", "")),
        shiny::div(class = "pl-editor-actions", shiny::actionButton("run_evidence_reset", "Werte dieses Assets zurücksetzen", class = "btn-default"))),
      shiny::uiOutput("run_evidence_list")),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("run_prepare", "Abschlussplan prüfen", class = "btn-default"),
      shiny::checkboxInput("run_confirm", "Genau diesen Abschluss einmalig bestätigen", FALSE),
      shiny::actionButton("run_execute", "Bestätigten Abschluss starten", class = "btn-primary"),
      shiny::actionButton("run_resume", "Bestätigten Abschluss fortsetzen", class = "btn-default"),
      shiny::actionButton("run_result_refresh", "Publizierten Stand lesen", class = "btn-default")
    ),
    # Ohne dieses Feld schrieb "Run-Plan pruefen" seine Meldung in den
    # Meldungsspeicher, aus dem sie niemand las: Der Knopf blieb stumm, ob der
    # Plan nun entstand oder an einer Eingabe scheiterte. Die Karte darueber
    # zeigt den zuletzt ausgefuehrten Lauf, nicht diesen Versuch
    # (Befund 28.09.2026).
    shiny::uiOutput("run_action_feedback"),
    shiny::uiOutput("run_publication_status"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("run_preview")),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("run_stages"))
  )
)

# "Alles aktualisieren" (#368): von jedem Reiter aus erreichbar, seit rc.366 (#540) im Block links statt in der Kopfzeile. Der Knopf
# klappt den Bereich ueber dem Inhalt auf und zu und meldet das als Eingabe refresh_all_panel_open; erst dann werden die Staende gelesen.
data_refresh_all_toggle_v1 <- function() shiny::tags$button(type = "button", id = "refresh_all_toggle", class = "btn btn-primary",
  onclick = paste0("var p=document.getElementById('refresh-all-panel');var open=p.hasAttribute('hidden');",
                   "var s=document.getElementById('settings-panel');if(open&&s&&!s.hasAttribute('hidden')){document.getElementById('settings_toggle').click();}",
                   "if(open){p.removeAttribute('hidden');p.scrollIntoView({behavior:'smooth',block:'start'});}else{p.setAttribute('hidden','');}",
                   "if(window.Shiny&&Shiny.setInputValue){Shiny.setInputValue('refresh_all_panel_open',open,{priority:'event'});}",
                   "$(p).trigger(open?'shown':'hidden');"),
  "Alles aktualisieren")
# Einstellungen (#519, rc.332, Festlegung 26./27.10.2026): Sie gelten fuer alle Apps, nicht fuer einen Fachbereich, und standen
# bis rc.331 als Reiter hinter "Steuer", bis rc.365 in der Kopfzeile, seit rc.366 (#540) im Block links aller Apps. Wie "Alles
# aktualisieren" klappt der Knopf einen Bereich auf und meldet settings_panel_open; erst dann werden Einstellungen, Zeitplan und
# Speichergroesse gelesen.
data_settings_toggle_v1 <- function() shiny::tagList(shiny::tags$button(type = "button", id = "settings_toggle", class = "btn btn-default",
  onclick = paste0("var p=document.getElementById('settings-panel');var open=p.hasAttribute('hidden');",
                   "var r=document.getElementById('refresh-all-panel');if(open&&r&&!r.hasAttribute('hidden')){document.getElementById('refresh_all_toggle').click();}",
                   "if(open){p.removeAttribute('hidden');p.scrollIntoView({behavior:'smooth',block:'start'});}else{p.setAttribute('hidden','');}",
                   "if(window.Shiny&&Shiny.setInputValue){Shiny.setInputValue('settings_panel_open',open,{priority:'event'});}",
                   "$(p).trigger(open?'shown':'hidden');"),
  "Einstellungen"),
  # Nach dem Speichern klappt der Bereich zu (rc.333, Festlegung 27.10.2026); die Rueckmeldung steht dann kurz hier.
  shiny::tags$span(id = "settings_flash", class = "pl-field-hint", role = "status", `aria-live` = "polite"))
# Zuklappen: "Fertig" unten im Bereich und nach erfolgreichem "Einstellungen speichern" (Nachricht pl_settings_done vom Server).
data_settings_close_v1 <- function() shiny::tagList(
  shiny::div(class = "pl-editor-actions",
    shiny::tags$button(type = "button", id = "settings_close", class = "btn btn-default",
      onclick = "var p=document.getElementById('settings-panel');if(p&&!p.hasAttribute('hidden')){document.getElementById('settings_toggle').click();}",
      "Fertig · zuklappen")),
  shiny::tags$script(shiny::HTML(paste0(
    "$(document).on('shiny:connected',function(){Shiny.addCustomMessageHandler('pl_settings_done',function(m){",
    "var p=document.getElementById('settings-panel');if(p&&!p.hasAttribute('hidden')){document.getElementById('settings_toggle').click();}",
    "var f=document.getElementById('settings_flash');if(f){f.textContent=(m&&m.text)||'';clearTimeout(window.__plSettingsFlash);",
    "window.__plSettingsFlash=setTimeout(function(){f.textContent='';},6000);}});});"))))

ui <- portelyra_app_shell(
  "data", "Assets und Portfolio-Daten verständlich pflegen",
  "Transaktionen, Stammdaten, Marktdaten und Steuer bleiben übersichtlich getrennt; „Alles aktualisieren“ bringt alle Ergebnisse auf den neuesten Stand. Jede Datenaktion erfordert ihre eigene Bestätigung.",
  capabilities = c("Lokal, ein Nutzer", "Geführter Asset-Prozess", "Getrennte Grenzen für Vorschau und Schreiben"),
  actions = data_when_needed_v1("action_failed", shiny::actionButton("read_workspace", "Daten neu lesen", class = "btn-default"), inline = TRUE),
  # Aktualisierung, „Läuft gerade“ und Einstellungen links (#540): hier klappen die Knoepfe die Bereiche auf.
  sidebar_activity = shiny::tagList(desktop_activity_sidebar_ui_v1(data_refresh_all_toggle_v1(), data_settings_toggle_v1(), help_app = "data",
    version = desktop_program_version_v1(project_root), notes_action = data_program_notes_link_v1()), data_activity_open_from_hash_v1()),
  sidebar_status = shiny::tagList(shiny::strong("Lokaler Runtime-/Aktionsstatus"),
    shiny::p("Letzte Aktion · keine pauschale Portfolio-Freigabe"), shiny::uiOutput("runtime_status")),
  shiny::div(id = "refresh-all-panel", hidden = NA,
    data_refresh_all_card_ui_v1(),
    data_when_needed_v1("history_halted", shiny::tags$details(class = "pl-disclosure", shiny::tags$summary("Einzelne Schritte · Tageshistorie fortschreiben"),
      desktop_data_sections$history))),
  shiny::div(id = "settings-panel", hidden = NA,
    shiny::tags$h2("Einstellungen"),
    shiny::p(class = "pl-section-copy", "Gelten für alle Apps: Portfolios und ihr Umfang, Anzeige, Expertenwerkzeuge, Aufbewahrung, Zugänge für Plugins, Zeitplan für „Alles aktualisieren“, Speicher, Version und Browser. Steuerliche Einstellungen stehen im Reiter „4. Steuer“."),
    # Umfang dieses Portfolios (#542) unter "Portfolios" (#547). Unterreiter: der Bereich bleibt
    # aus jeder App erreichbar, innen gegliedert. Die Karten der Anzeige teilen einen Speichern-Knopf und stehen deshalb zusammen.
    shiny::tabsetPanel(id = "settings_tabs",
      shiny::tabPanel("Portfolio", value = "portfolio", data_portfolio_settings_ui_v1(), data_portfolio_configuration_ui_v1()),
      shiny::tabPanel("Anzeige und Berechnung", value = "display", data_user_settings_ui_v1()),
      shiny::tabPanel("Automatik", value = "schedule", data_refresh_all_schedule_ui_v1()),
      shiny::tabPanel("Sicherheit und Speicher", value = "security", data_protection_ui_v1(), data_backups_ui_v1(), data_storage_retention_ui_v1()),
      shiny::tabPanel("Plugins und Zugänge", value = "plugins", data_plugin_manager_ui_v1(), data_plugin_credentials_ui_v1()),
      # Programm (#562, #586; 0.3.3): Version, „Neu in dieser Version“, Browser - je Installation, nicht je Portfolio.
      shiny::tabPanel("Programm", value = "program", data_program_ui_v1())),
    data_settings_close_v1()),
  # Einmal nach einem Update (#562): „Neu in Version …“; leer ohne Platz. Danach, solange unbeantwortet, die Frage nach der Update-Suche.
  data_program_whats_new_slot_v1(),
  data_program_consent_slot_v1(),
  # Gefuehrte Einrichtung (#542): erscheint von selbst fuer ein Portfolio, das noch nicht eingerichtet ist.
  data_portfolio_setup_ui_v1(),
  portelyra_card("Assets pflegen", class = "pl-write-boundary",
    data_asset_center_ui_v1(
      transactions = shiny::tagList(
        shiny::tags$style(shiny::HTML(".pl-subtabs>.tabbable>.nav-tabs>li>a{font-size:.95em;padding:6px 14px}")),
        # Bausteine (#542): "Eingang", "Import" und "Leser" nur mit Belegen (#583: ein Schalter, ohne ihn wird von Hand gebucht),
        # "Kursanbieter" nur mit Marktdaten.
        shiny::div(class = "pl-workspace-tabs pl-subtabs", data_module_tabs_v1(shiny::tabsetPanel(id = "transactions_view",
          # Die Asset-Suche steht hier, weil sie Formular und Buchungsliste fuehrt (#424, rc.332).
          shiny::tabPanel("Manuell", value = "manual", data_asset_context_slot_v1(), desktop_transactions_mode_ui_v1(),
            shiny::conditionalPanel("input.transactions_mode != 'cash'", desktop_data_sections$manual),
            shiny::conditionalPanel("input.transactions_mode == 'cash'", desktop_data_sections$cash),
            shiny::conditionalPanel("input.transactions_mode == 'fx'", desktop_fx_mode_note_v1())),
          # Monatlicher Eingang (#513): Belegordner pruefen, je Institut ablegen, dann im Import buchen.
          shiny::tabPanel("Eingang", value = "intake", data_statement_intake_ui_v1()),
          shiny::tabPanel("Import", value = "import", desktop_import_kind_ui_v1(),
            shiny::conditionalPanel("['securities','crypto','fx'].indexOf(input.import_kind) >= 0", desktop_data_sections$securities_import),
            shiny::conditionalPanel("input.import_kind == 'rewards'", desktop_data_sections$statements, data_reference_backfill_card_ui_v1()),
            shiny::conditionalPanel("input.import_kind == 'cash'", desktop_data_sections$cash_import)),
          # Bis rc.297 im Reiter "5. Abschluss" (#368): FIFO-Stand pruefen, Bestand ansehen, Pflegestand je Asset und Konto.
          shiny::tabPanel("Bestand prüfen", value = "completion", shiny::div(id = "data-portfolio-completion", desktop_data_sections$completion)),
          # Leser (rc.380, #486): je Leser Version, Pruefsumme, an Ihren Belegen geprueft, Buchungen; Selbsttest auf Knopfdruck.
          shiny::tabPanel("Leser", value = "readers", data_statement_readers_ui_v1()),
          # Kursanbieter (rc.383, #495): fuer alle Portfolios gemeinsam aktivieren, Adressen, Kosten, Bedingungen, Abschottung, Selbsttest.
          shiny::tabPanel("Kursanbieter", value = "price_providers", data_price_providers_ui_v1())),
          list(intake = data_module_condition_v1("documents"), import = data_module_condition_v1("documents"),
               readers = data_module_condition_v1("documents"), price_providers = data_module_condition_v1("market_data")))),
        # Expertenwerkzeuge nur mit dem Schalter in den Einstellungen (#452, Vorgriff auf #492); geloescht wird nichts.
        data_expert_only_v1(
        shiny::tags$details(class="pl-disclosure", shiny::tags$summary("Expertenwerkzeuge · ältere Importwege, gekoppelte Alt-Transaktionen und synthetische Prüfungen"),
          desktop_data_sections$transactions, shiny::div(class="pl-table-wrap", shiny::tableOutput("workspace_transactions")),
          shiny::tags$details(id="data-quick-import", class="pl-disclosure", shiny::tags$summary("Quick Import und offene ActivityDrafts"), desktop_data_sections$quick_import),
          shiny::tags$details(id="data-setup-exchange", class="pl-disclosure", shiny::tags$summary("Portfolio-Datenaustausch (Paket)"), desktop_data_sections$exchange),
          desktop_data_sections$kraken_lab, desktop_data_sections$mapping_lab, desktop_data_sections$legacy))),
      # Unterreiter der Stammdaten (#422): Assets, Konten und Institute, Ablage, FIFO-Wallet, Anlage und Analyse.
      master_tools = list(
        top = shiny::tagList(
          data_when_needed_v1("setup", shiny::tags$details(class="pl-disclosure", open=NA, shiny::tags$summary("Ersteinrichtung · nur bei neuer, leerer Installation"), desktop_data_sections$setup)),
          # Portfolio anlegen und umbenennen stehen seit #547 in den Einstellungen; hier nur der Verweis, solange es keines gibt.
          data_when_signal_v1("portfolio", portelyra_status_panel("Noch kein Portfolio", "Ein Portfolio legen Sie in den Einstellungen an (Knopf „Einstellungen“ links, Abschnitt „Portfolios“).", tone = "neutral")),
          data_basis_names_ui_v1()),
        accounts = shiny::tagList(
          data_master_autoopen_v1(data_institution_master_ui_v1()),
          # Liest sich beim Aufklappen (#492, Festlegung 23.10.2026): Den Knopf "Daten neu lesen" gibt es nur noch nach Fehlern.
          shiny::tags$details(class="pl-disclosure pl-lazy", id="data_workspace_overview", shiny::tags$summary("Übersicht · Portfolios, Konten und Assets"), desktop_data_sections$workspace),
          data_expert_only_v1(shiny::tags$details(id="data-advanced-lab", class="pl-disclosure", shiny::tags$summary("Sonderfälle · Archivieren und Sammelanlage per CSV"), desktop_data_sections$catalog))),
        archive = data_master_autoopen_v1(data_statement_archive_ui_v1()),
        # FIFO-Wallet aus mehreren Konten (#508): ohne Schalter, damit der Hinweis auf betroffene Verkaeufe sichtbar ist.
        wallet = shiny::tagList(data_master_autoopen_v1(data_fifo_wallet_ui_v1()), data_expert_only_v1(data_crypto_method_ui_v1())),
        # Aktiensplit (#451): eine Kapitalmassnahme je Asset, neben dem Buchungsbestand gespeichert.
        corporate = data_master_autoopen_v1(data_stock_split_ui_v1()),
        settings = shiny::tagList(data_master_autoopen_v1(data_investment_scope_ui_v1()), data_master_autoopen_v1(data_analysis_settings_ui_v1()))),
      tax = data_tax_settings_ui_v1(institution_card = data_institution_tax_card_ui_v1(), advance_card = data_advance_lump_sum_card_ui_v1(),
                                    document_card = data_tax_document_card_ui_v1()),
      run_center = desktop_data_sections$run, snapshot_tools = data_snapshot_publish_ui_v1(),
      # Bewertung ueber die Zeit (rc.393, #495): unter "3. Marktdaten" -> "1. Kursquelle", neben der Bewertungsart.
      market_tools = data_asset_valuation_timeline_ui_v1())))

server <- function(input, output, session) {
  action_feedback <- new_data_action_feedback_v1(list(
    tone = "neutral", title = "Lokale Runtime bereit",
    copy = "Lokale Daten verbunden · noch nichts gelesen."
  ))
  state <- action_feedback$state
  for(area in c('method','candidate','probe','setup','refresh','promotion','verification','correction','import','draft','profile','run')) local({
    name <- area
    output[[paste0(name,'_action_feedback')]] <- shiny::renderUI(data_action_feedback_panel_v1(action_feedback$read(name)))
  })
  activity_completed <- shiny::reactiveVal(NULL)
  activity_workflow <- NULL
  activity_workflow_view <- shiny::reactiveVal(list(action="create",selected_refs=character(),dirty=FALSE,can_prepare=TRUE))
  activity_workflow_loading <- NULL
  activity_workflow_ticket <- NULL
  activity_workflow_completed <- shiny::reactiveVal(FALSE)
  activity_workflow_reset_pending <- FALSE
  workspace <- shiny::reactiveVal(NULL)
  # Leere Datenablage (#492): dann erscheint die Ersteinrichtung von selbst. Eine Dateipruefung, kein Leseaufruf.
  need_setup <- shiny::reactiveVal(!file.exists(runtime_canonical_path(runtime$context)))
  market_setup_failed <- shiny::reactiveVal(FALSE)
  transaction_editor <- new_data_transaction_editor_v1()
  transaction_catalog <- shiny::reactiveVal(NULL)
  transaction_preview <- shiny::reactiveVal(NULL)
  activity_adapter <- new_data_asset_activity_product_adapter_v1(project_root, runtime$context)
  activity_editor <- new_data_asset_activity_editor_v1(activity_adapter)
  activity_catalog <- shiny::reactiveVal(NULL)
  activity_read_view <- shiny::reactiveVal(NULL)
  activity_scope_selected <- shiny::reactiveVal(character())
  activity_scope_excluded <- shiny::reactiveVal(character())
  activity_scope_accounts <- shiny::reactiveVal(character())
  activity_scope_view_mode <- shiny::reactiveVal("all")
  activity_scope_domains <- shiny::reactiveVal("noncash")
  activity_scope_account_match <- shiny::reactiveVal("any")
  activity_scope_account_usage <- shiny::reactiveVal("current")
  activity_scope_interval_enabled <- shiny::reactiveVal(FALSE)
  activity_scope_interval_from <- shiny::reactiveVal(NULL)
  activity_scope_interval_to <- shiny::reactiveVal(NULL)
  activity_scope_interval_relation <- shiny::reactiveVal("activity")
  activity_scope_holding_mode <- shiny::reactiveVal("any_time")
  reset_activity_scope_controls <- function() {
    activity_scope_selected(character())
    activity_scope_excluded(character())
    activity_scope_accounts(character())
    activity_scope_view_mode("all")
    activity_scope_domains("noncash")
    activity_scope_account_match("any")
    activity_scope_account_usage("current")
    activity_scope_interval_enabled(FALSE)
    activity_scope_interval_from(NULL)
    activity_scope_interval_to(NULL)
    activity_scope_interval_relation("activity")
    activity_scope_holding_mode("any_time")
    shiny::updateSelectizeInput(session, "activity_scope_assets", selected = character())
    shiny::updateSelectizeInput(session, "activity_scope_excluded_assets", selected = character())
    shiny::updateSelectizeInput(session, "activity_scope_accounts", selected = character())
    shiny::updateRadioButtons(session, "activity_scope_mode", selected = "all")
    shiny::updateCheckboxGroupInput(session, "activity_scope_domain", selected = "noncash")
    shiny::updateRadioButtons(session, "activity_scope_account_match", selected = "any")
    shiny::updateRadioButtons(session, "activity_scope_account_usage", selected = "current")
    shiny::updateCheckboxInput(session, "activity_scope_interval_enabled", value = FALSE)
    session$sendInputMessage("activity_scope_interval_from", list(value = ""))
    session$sendInputMessage("activity_scope_interval_to", list(value = ""))
    shiny::updateRadioButtons(session, "activity_scope_interval_relation", selected = "activity")
    shiny::updateRadioButtons(session, "activity_scope_holding_mode", selected = "any_time")
    invisible(TRUE)
  }
  activity_preview <- shiny::reactiveVal(NULL)
  activity_approval <- shiny::reactiveVal(NULL)
  activity_context_block <- shiny::reactiveVal(NULL)
  asset_center_selected_ref <- ""
  asset_center_choices_sent <- NULL
  # Die Vorauswahl, die die Asset-Suche ohne Wahl des Nutzers trifft (erstes Asset der Liste). Ihr folgt die Buchungsart nicht.
  # Der Asset-Filter der Sitzung. Die Kopie am Server ist massgeblich: Nach einem
  # Neulesen des Katalogs koennen die Konto-Refs andere sein, und der Browser
  # erfaehrt das erst einen Durchlauf spaeter.
  asset_center_filter <- data_asset_center_filter_input_v1()
  asset_center_filter_options_sent <- NULL
  asset_center_filter_status <- shiny::reactiveVal(NULL)
  asset_center_selected_portfolio_ref <- ""
  # Reiner Anzeigezustand. Die Generationsbelege bleiben davon unberuehrt; ein
  # neuer Korrektur-/Stornobeleg blendet die Tabelle wieder ein.
  correction_history_hidden <- shiny::reactiveVal(FALSE)
  activity_last_successful_context <- shiny::reactiveVal(NULL)
  correction_adapter <- new_data_asset_activity_correction_product_adapter_v1(project_root, runtime$context)
  correction_center <- new_data_asset_activity_correction_center_v1(correction_adapter)
  correction_model <- shiny::reactiveVal(NULL)
  correction_preview <- shiny::reactiveVal(NULL)
  # Die Reihe der Sammelbearbeitung (#424): geordnete Buchungsschluessel, die
  # Stelle, an der sie steht, und was bei den bereits durchgegangenen Buchungen
  # herauskam.
  activity_sequence <- shiny::reactiveVal(NULL)
  activity_sequence_report <- shiny::reactiveVal(NULL)
  activity_sequence_discard <- shiny::reactiveVal(FALSE)
  # Die Zeilenschluessel, die der Server nach einer eigenen, geschriebenen
  # Korrektur freigegeben hat. Der Browser meldet sie weiter, bis der Eigentuemer
  # die naechste Zeile anklickt - sie zeigen aber auf eine Generation, die es
  # nicht mehr gibt.
  activity_rows_released <- shiny::reactiveVal(character())
  # Zaehlt nach jedem gespeicherten Beleg hoch; die Tabelle liest die Angaben dann neu.
  activity_reference_tick <- shiny::reactiveVal(0L)
  activity_reference_notice <- shiny::reactiveVal(NULL)
  # Die Meldung ueber den zuletzt geschriebenen Schritt, wenn der Server danach
  # selbst zur Neuanlage zurueckgekehrt ist. Sie haengt nicht am Rueckmeldekanal
  # der Korrektur: Den leert jede Aenderung an der Maske, und die erste Aenderung
  # nach dem Schritt ist das Leeren der Maske durch den Server selbst.
  activity_release_notice <- shiny::reactiveVal(NULL)
  correction_approval <- shiny::reactiveVal(NULL)
  scale_adapter <- new_data_asset_quantity_scale_product_adapter_v1(project_root, runtime$context)
  scale_center <- new_data_asset_quantity_scale_center_v1(scale_adapter)
  scale_preview <- shiny::reactiveVal(NULL)
  scale_pending <- shiny::reactiveVal(NULL)
  realized_adapter <- new_data_realized_state_product_adapter_v2(project_root, runtime$context)
  realized_model <- shiny::reactiveVal(NULL)
  realized_parity <- shiny::reactiveVal(NULL)
  portfolio_completion_notice <- shiny::reactiveVal(NULL)
  readiness_model <- shiny::reactiveVal(NULL)
  activity_csv_adapter <- new_data_asset_activity_csv_product_adapter_v1(project_root,runtime$context)
  activity_csv_center <- new_data_asset_activity_csv_center_v1(activity_csv_adapter)
  activity_csv_inspection <- shiny::reactiveVal(NULL)
  activity_csv_preview <- shiny::reactiveVal(NULL)
  activity_csv_resumable <- shiny::reactiveVal(NULL)
  activity_draft_adapter <- new_data_activity_draft_product_adapter_v1(project_root,runtime$context)
  activity_draft_center <- new_data_activity_draft_center_v1(activity_draft_adapter)
  activity_quick_draft_center <- new_data_activity_draft_center_v1(activity_draft_adapter)
  activity_quick_center <- new_data_activity_quick_import_v1(activity_draft_adapter,activity_quick_draft_center,activity_editor)
  activity_quick_inspection <- shiny::reactiveVal(NULL)
  activity_quick_prepared <- shiny::reactiveVal(NULL)
  activity_quick_profiles <- shiny::reactiveVal(NULL)
  activity_quick_loaded_profile <- shiny::reactiveVal(NULL)
  statement_workspace_center <- new_data_statement_import_workspace_v1(project_root,runtime$context)
  statement_workspace_result <- shiny::reactiveVal(NULL)
  statement_workspace_state <- shiny::reactiveVal(data_statement_import_workspace_status_v1())
  statement_mapping_center <- new_data_statement_import_mapping_v1(project_root)
  statement_mapping_result <- shiny::reactiveVal(NULL)
  statement_mapping_state <- shiny::reactiveVal(data_statement_import_mapping_status_v1())
  statement_exchange_preview <- shiny::reactiveVal(NULL)
  statement_exchange_mapping <- shiny::reactiveVal(NULL)
  statement_exchange_profile <- shiny::reactiveVal(NULL)
  statement_exchange_selected_refs <- shiny::reactiveVal(NULL)
  statement_exchange_handoff <- shiny::reactiveVal(NULL)
  statement_exchange_booked <- shiny::reactiveVal(character())
  statement_guided_result <- shiny::reactiveVal(NULL)
  # Was aus frueheren Laeufen offen gespeichert ist, unabhaengig von dieser
  # Sitzung und von einer vorgelegten Datei (#422).
  statement_resume_groups <- shiny::reactiveVal(NULL)
  statement_resume_active <- shiny::reactiveVal(NULL)
  statement_resume_notice <- shiny::reactiveVal(NULL)
  statement_reward_valuation_batch <- shiny::reactiveVal(NULL)
  statement_reward_valuation_open <- shiny::reactiveVal(NULL)
  statement_reward_market_preview <- shiny::reactiveVal(NULL)
  statement_reward_market_batch_preview <- shiny::reactiveVal(NULL)
  statement_reward_market_batch_result <- shiny::reactiveVal(NULL)
  statement_reward_validation_preview <- shiny::reactiveVal(NULL)
  statement_reward_validation_result <- shiny::reactiveVal(NULL)
  statement_reward_collision_preview <- shiny::reactiveVal(NULL)
  statement_reward_collision_result <- shiny::reactiveVal(NULL)
  statement_reward_canonical_preview <- shiny::reactiveVal(NULL)
  statement_reward_canonical_result <- shiny::reactiveVal(NULL)
  statement_reward_market_service <- new_data_reward_daily_close_service_v1(project_root,runtime$context)
  statement_exchange_state <- shiny::reactiveVal(data_statement_exchange_preview_status_v1())
  statement_status_panel <- function(item) {
    tone<-if(identical(item$tone,"success"))"positive"else if(item$tone%in%c("blocked","error"))"error"else if(identical(item$tone,"warning"))"warning"else"neutral"
    portelyra_status_panel(item$title,item$copy,tone=tone)
  }
  # Quelle des geladenen Stapels (#520): Ein fortgesetzter Lauf hat keine Datei. Ohne gemerkte Quelle scheiterte jeder Schritt nach
  # dem Laden - Pruefen, Kurse uebernehmen, Wert eintragen -, nachdem er schon geschrieben hatte. Bleibt serverseitig.
  statement_batch_source <- shiny::reactiveVal(NULL)
  reset_statement_reward_steps<-function(){
    statement_batch_source(NULL)
    statement_exchange_handoff(NULL);statement_exchange_booked(character());statement_guided_result(NULL);statement_reward_valuation_batch(NULL);statement_reward_valuation_open(NULL)
    statement_reward_market_preview(NULL);statement_reward_market_batch_preview(NULL);statement_reward_market_batch_result(NULL)
    statement_reward_validation_preview(NULL);statement_reward_validation_result(NULL);statement_reward_collision_preview(NULL);statement_reward_collision_result(NULL)
    statement_reward_canonical_preview(NULL);statement_reward_canonical_result(NULL)
    shiny::updateCheckboxInput(session,"statement_reward_collision_confirm",value=FALSE)
  }
  activity_draft_list <- shiny::reactiveVal(NULL)
  activity_draft_reasons <- shiny::reactiveVal(list())
  activity_draft_open <- shiny::reactiveVal(NULL)
  activity_draft_approval <- shiny::reactiveVal(NULL)
  activity_draft_completed <- shiny::reactiveVal(NULL)
  cash_adapter <- new_data_cash_coverage_product_adapter_v1(project_root, runtime$context)
  cash_editor <- new_data_cash_coverage_editor_v1(cash_adapter)
  cash_catalog <- shiny::reactiveVal(NULL)
  cash_read_view <- shiny::reactiveVal(NULL)
  cash_preview <- shiny::reactiveVal(NULL)
  cash_recovery_preview <- shiny::reactiveVal(NULL)
  catalog_editor <- new_desktop_catalog_editor_v1()
  catalog_model <- shiny::reactiveVal(NULL)
  catalog_preview <- shiny::reactiveVal(NULL)
  asset_center_catalog_editor <- new_desktop_catalog_editor_v1()
  asset_center_catalog <- shiny::reactiveVal(NULL)
  asset_center_core_preview <- shiny::reactiveVal(NULL)
  asset_center_price_currency_preview <- shiny::reactiveVal(NULL)
  asset_center_edit_preview <- shiny::reactiveVal(NULL)
  asset_center_defaults_notice <- shiny::reactiveVal('Währungsvorschlag ist unbestätigt; Handelsplatz und Quotierungseinheit prüfen.')
  asset_center_currency_auto_value <- NULL
  asset_center_pending_draft <- NULL
  market_worklist_service <- new_data_market_worklist_service_v1(project_root, runtime$context)
  # Anbieter mit Tageskursen bzw. Momentkurs aus den Plugin-Manifesten (rc.394, #495).
  price_provider_operations <- data_price_provider_operations_v1(project_root)
  asset_center_provider_editor <- new_data_provider_mapping_editor_v1(
    history_providers = data_price_providers_with_v1(price_provider_operations, "daily_history"),
    quote_providers = data_price_providers_with_v1(price_provider_operations, "quote"))
  asset_center_provider_catalog <- shiny::reactiveVal(NULL)
  asset_center_provider_preview <- shiny::reactiveVal(NULL)
  asset_center_provider_search_service <- new_data_provider_search_service_v1(project_root, runtime$context)
  asset_center_fx_search_service <- new_data_provider_search_service_v1(project_root, runtime$context)
  asset_center_fx_search_preview <- shiny::reactiveVal(NULL)
  asset_center_fx_search_result <- shiny::reactiveVal(NULL)
  asset_center_fx_probe_service <- new_data_fx_pair_probe_service_v1(project_root, runtime$context)
  asset_center_fx_probe_preview <- shiny::reactiveVal(NULL)
  asset_center_fx_probe_result <- shiny::reactiveVal(NULL)
  asset_center_fx_promotion_service <- new_data_fx_pair_promotion_service_v1(project_root, runtime$context)
  asset_center_fx_promotion_preview <- shiny::reactiveVal(NULL)
  asset_center_fx_promotion_result <- shiny::reactiveVal(NULL)
  asset_center_fx_history_service <- new_data_fx_history_review_service_v1(project_root, runtime$context)
  asset_center_fx_history_plan <- shiny::reactiveVal(NULL)
  asset_center_fx_history_preview <- shiny::reactiveVal(NULL)
  asset_center_fx_history_review <- shiny::reactiveVal(NULL)
  asset_center_fx_history_publication <- shiny::reactiveVal(NULL)
  asset_center_fx_attempts <- shiny::reactiveVal(NULL)
  asset_center_calendar_gap_service <- new_data_market_calendar_gap_service_v1(project_root, runtime$context)
  asset_center_calendar_gaps <- shiny::reactiveVal(NULL)
  asset_center_calendar_targets <- shiny::reactiveVal(list())
  asset_center_calendar_review_service <- new_data_calendar_gap_review_service_v1(project_root,runtime$context)
  asset_center_calendar_binding_preview <- shiny::reactiveVal(NULL)
  asset_center_calendar_correction_preview <- shiny::reactiveVal(NULL)
  asset_center_calendar_batch_preview <- shiny::reactiveVal(NULL)
  asset_center_calendar_feedback <- shiny::reactiveVal(NULL)
  asset_center_calendar_bound <- shiny::reactiveVal(FALSE)
  asset_center_provider_search_preview <- shiny::reactiveVal(NULL)
  asset_center_provider_search_result <- shiny::reactiveVal(NULL)
  asset_center_provider_probe_service <- new_data_provider_probe_service_v1(project_root, runtime$context)
  asset_center_provider_probe_preview <- shiny::reactiveVal(NULL)
  asset_center_provider_probe_result <- shiny::reactiveVal(NULL)
  asset_center_provider_promotion_service <- new_data_provider_promotion_service_v1(project_root, runtime$context)
  asset_center_provider_promotion_preview <- shiny::reactiveVal(NULL)
  asset_center_provider_promotion_result <- shiny::reactiveVal(NULL)
  asset_center_mapping_verify_preview <- shiny::reactiveVal(NULL)
  asset_center_market_plan_service <- new_data_market_history_plan_service_v1(project_root, runtime$context)
  asset_center_market_coverage_service <- new_data_market_history_coverage_service_v1(project_root, runtime$context)
  asset_center_fx_coverage_service <- new_data_fx_demand_coverage_service_v1(project_root, runtime$context)
  asset_center_market_coverage <- shiny::reactiveVal(NULL)
  asset_center_fx_coverage <- shiny::reactiveVal(NULL)
  asset_center_completion_plan <- shiny::reactiveVal(NULL)
  asset_center_completion_batch <- shiny::reactiveVal(NULL)
  asset_center_batch_service <- new_data_market_fx_batch_service_v1(project_root, runtime$context)
  asset_center_valuation_service <- new_data_market_valuation_service_v1(project_root, runtime$context)
  asset_center_manual_price_service <- new_data_manual_price_service_v1(project_root, runtime$context)
  activity_reference_service <- new_data_activity_reference_service_v1(project_root, runtime$context)
  # Laesst sich der Dienst der Kontonummern nicht anlegen, bleibt die uebrige App benutzbar; der Bereich sagt es.
  account_reference_service <- tryCatch(new_data_account_reference_service_v1(project_root, runtime$context), error = function(error) NULL)
  institution_tax_service <- tryCatch(new_data_institution_tax_service_v1(project_root, runtime$context), error = function(error) NULL)
  institution_master_service <- tryCatch(new_data_institution_master_service_v1(project_root, runtime$context), error = function(error) NULL)
  investment_scope_service <- tryCatch(new_data_investment_scope_service_v1(project_root, runtime$context), error = function(error) NULL)
  analysis_settings_service <- tryCatch(new_data_analysis_settings_service_v1(project_root, runtime$context), error = function(error) NULL)
  user_settings_service <- tryCatch(new_data_user_settings_service_v1(project_root, runtime$context), error = function(error) NULL)
  storage_retention_service <- tryCatch(new_data_storage_retention_service_v1(project_root, runtime$context), error = function(error) NULL)
  crypto_method_service <- tryCatch(new_data_crypto_method_service_v1(project_root, runtime$context), error = function(error) NULL)
  fifo_wallet_service <- tryCatch(new_data_fifo_wallet_service_v1(project_root, runtime$context), error = function(error) NULL)
  stock_split_service <- tryCatch(new_data_stock_split_service_v1(project_root, runtime$context), error = function(error) NULL)
  advance_lump_sum_service <- tryCatch(new_data_advance_lump_sum_service_v1(project_root, runtime$context), error = function(error) NULL)
  # Ertraegnisaufstellung (#459, #465): Betraege laut Beleg und Bruttozinsen.
  tax_document_service <- tryCatch(new_data_tax_document_service_v1(project_root, runtime$context), error = function(error) NULL)
  statement_archive_service <- tryCatch(new_data_statement_archive_service_v1(project_root, runtime$context), error = function(error) NULL)
  asset_center_carry_service <- new_data_market_history_carry_service_v1(project_root, runtime$context)
  asset_center_manual_prices <- shiny::reactiveVal(NULL)
  asset_center_market_plan <- shiny::reactiveVal(NULL)
  asset_center_market_review_service <- new_data_market_history_review_service_v1(project_root, runtime$context)
  asset_center_market_fetch_preview <- shiny::reactiveVal(NULL)
  asset_center_market_fetch_result <- shiny::reactiveVal(NULL)
  asset_center_market_review <- shiny::reactiveVal(NULL)
  asset_center_market_publication_result <- shiny::reactiveVal(NULL)
  asset_center_provider_online <- shiny::reactiveVal(list(
    tone = "neutral", title = "Kein Kursabruf gestartet",
    copy = "Suche und Testabruf benötigen später eine separate ausdrückliche Live-Freigabe."
  ))
  asset_center_tax_catalog <- shiny::reactiveVal(NULL)
  asset_center_tax_overview <- shiny::reactiveVal(NULL)
  asset_center_tax_preview <- shiny::reactiveVal(NULL)
  asset_center_tax_state <- shiny::reactiveVal("not_initialized")
  asset_center_history_state <- shiny::reactiveVal("not_requested")
  asset_center_activity_state <- shiny::reactiveVal("not_checked")
  product_data_root <- dirname(dirname(dirname(runtime_data_space_path(runtime$context))))
  asset_center_tax_service <- new_tax_ui_service_v1(
    project_root, product_data_root,
    list(tenant_id = runtime$context$tenant_id, user_id = runtime$context$user_id, data_space_id = runtime$context$data_space_id)
  )
  if (isTRUE(asset_center_tax_service$initialized())) asset_center_tax_state("not_configured")
  portfolio_exchange_service <- new_data_portfolio_csv_exchange_v1(project_root, runtime$context)
  portfolio_exchange_paths_model <- shiny::reactiveVal(NULL)
  portfolio_exchange_export_model <- shiny::reactiveVal(NULL)
  portfolio_exchange_import_list <- shiny::reactiveVal(NULL)
  portfolio_exchange_import_model <- shiny::reactiveVal(NULL)
  portfolio_exchange_staged_list <- shiny::reactiveVal(NULL)
  portfolio_exchange_handoff_model <- shiny::reactiveVal(NULL)
  portfolio_exchange_recovery_list <- shiny::reactiveVal(NULL)
  portfolio_exchange_recovery_model <- shiny::reactiveVal(NULL)
  portfolio_exchange_cash_list <- shiny::reactiveVal(NULL)
  portfolio_exchange_cash_model <- shiny::reactiveVal(NULL)
  catalog_csv_center <- spotcore::new_desktop_csv_import_v1()
  catalog_csv_model <- shiny::reactiveVal(NULL)
  catalog_csv_preview <- shiny::reactiveVal(NULL)
  run_center <- spotcore::new_desktop_run_center_v1()
  run_catalog <- shiny::reactiveVal(NULL)
  run_preview <- shiny::reactiveVal(NULL)
  run_evidence_store <- shiny::reactiveVal(list())     # asset_ref -> Felder, nur Assets mit Abweichung von der Vorgabe
  run_evidence_current <- shiny::reactiveVal(NULL)     # das Asset, dessen Werte die Felder gerade zeigen
  run_valuations <- shiny::reactiveVal(list())
  published_workflow <- shiny::reactiveVal(desktop_workflow_display_state_v1())
  published_workflow_loaded <- FALSE
  now_utc <- function() format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  per_asset_source_adapter <- new_data_per_asset_legacy_review_fixture_adapter_if_available_v1(project_root, runtime$context)
  per_asset_product_adapter <- tryCatch(
    new_data_per_asset_legacy_review_product_adapter_v1(project_root, runtime$context, per_asset_source_adapter),
    spot_per_asset_review_error=function(error) NULL,
    error=function(error) NULL
  )
  activity_republication_adapter <- tryCatch(
    new_data_asset_activity_republication_adapter_v1(project_root, runtime$context),
    error=function(error) NULL
  )
  per_asset_review_center <- new_data_per_asset_review_center_v1(
    runtime$context,
    if (is.null(per_asset_product_adapter)) per_asset_source_adapter else per_asset_product_adapter$source_adapter
  )
  per_asset_review_module <- data_per_asset_legacy_review_module_server_v1(
    "per_asset_review", per_asset_review_center, clock=now_utc,
    product_adapter=per_asset_product_adapter
  )

  add_seconds <- function(value, seconds) {
    parsed <- as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    format(parsed + seconds, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  }
  safe <- function(expression, success) {
    tryCatch(
      .desktop_product_force_before_success_v1(expression, success),
      error = function(error) {
        # Der Kern hat abgelehnt und der Grund ist bekannt: Dann steht er da, statt
        # "Aktion blockiert" mit einem Sammelcode (#420).
        if (inherits(error, "spot_desktop_product_block_reason_error")) {
          state(list(tone = "warning", title = error$title, copy = error$copy))
          return(invisible(NULL))
        }
        code <- spotcore::desktop_product_safe_error_code_v1(error)
        # Ein paar Codes bedeuten schlicht "es fehlt eine Eingabe". Sie als
        # blockierte Aktion mit Codenummer zu zeigen, verschleiert das (23.09.2026).
        hint <- switch(code,
          asset_center_search_query_required = "Bitte zuerst einen Suchtext eintragen — Firma, ISIN oder Symbol.",
          desktop_provider_search_credential_unavailable = "Für diesen Suchanbieter ist kein bereiter Zugang eingetragen. Den Schlüssel unter Einstellungen → Plugins und Zugänge → Zugänge eintragen (oder dort den Zustand prüfen); bis dahin mit Yahoo suchen.",
          desktop_provider_search_cost_limit = "Die Obergrenze an Abrufen dieses Suchanbieters ist erreicht, oder er hat wegen zu vieler Abrufe abgewiesen. Morgen erneut versuchen, die Grenze unter Kursanbieter → Kosten anheben oder mit Yahoo suchen.",
          asset_center_market_method_invalid = "Für dieses Asset ist keine Marktbewertung über einen Kursanbieter eingestellt. Die Methode oben umstellen und speichern.",
          asset_center_market_selection_invalid = "Bitte oben eine gespeicherte Zuordnung auswählen.",
          asset_center_refresh_required = "Bitte zuerst das Asset-Center lesen.",
          desktop_catalog_isin_invalid = "Die Prüfziffer der ISIN stimmt nicht. Bitte die ISIN aus der Abrechnung übernehmen (zwölf Zeichen, etwa US0378331005).",
          desktop_catalog_isin_taken = "Diese ISIN steht schon an einem anderen Asset. Der Katalog führt je Papier ein Asset; dasselbe Papier in einem zweiten Depot bekommt sie nicht.",
          desktop_run_center_input_invalid = "Der Abschlussplan wurde abgewiesen, ohne dass die Vorprüfung das Feld benennen konnte. Bitte „Abschluss-Eingaben lesen“ erneut ausführen und den Plan noch einmal prüfen; bleibt es dabei, liegt es an einer Eingabe außerhalb der geprüften Regeln.",
          NULL)
        # Zugang oder Kosten eines Kursanbieters beim Testabruf oder Historienabruf (rc.394): derselbe Grund wie bei der Suche.
        if (is.null(hint) && endsWith(code, "_credential_unavailable"))
          hint <- "Für diesen Kursanbieter ist kein bereiter Zugang eingetragen. Den Schlüssel unter Einstellungen → Plugins und Zugänge → Zugänge eintragen oder dort den Zustand prüfen."
        if (is.null(hint) && endsWith(code, "_scheduled_disabled"))
          hint <- "Im täglichen Zeitlauf ist dieser Kursanbieter nicht freigegeben. Von Hand holt „Alles aktualisieren“ die Kurse; für den Zeitlauf unter Kursanbieter → Kosten „Im täglichen Zeitlauf abrufen“ einschalten."
        if (is.null(hint) && endsWith(code, "_cost_limit"))
          hint <- "Die Obergrenze an Abrufen dieses Kursanbieters ist erreicht, oder er hat wegen zu vieler Abrufe abgewiesen. Morgen erneut versuchen oder die Grenze unter Kursanbieter → Kosten anheben."
        # Kursanbieter nicht aktiv (rc.383): der genaue Grund statt "Aktion blockiert".
        provider_block <- data_price_provider_block_text_v1(code)
        if (!is.null(provider_block)) {
          state(list(tone = "warning", title = "Kursanbieter nicht aktiv", copy = paste0(provider_block, " (", code, ")")))
          return(invisible(NULL))
        }
        state(list(tone = if (is.null(hint)) "error" else "warning",
          title = if (is.null(hint)) "Aktion blockiert" else if (startsWith(code, "desktop_catalog_isin_")) "Eingabe prüfen"
            else if (endsWith(code, "_credential_unavailable")) "Zugang fehlt"
            else if (endsWith(code, "_cost_limit")) "Obergrenze erreicht"
            else if (endsWith(code, "_scheduled_disabled")) "Im Zeitlauf nicht freigegeben" else "Eingabe fehlt",
          copy = if (is.null(hint)) pl_error_text_v1(code) else paste0(hint, " (", code, ")")))
      }
    )
  }
  read_workspace <- function() {
    model <- spotcore::desktop_product_workspace_v1(runtime)
    workspace(model)
    state(list(
      tone = "neutral", title = "Daten gelesen",
      copy = if (model$status == "uninitialized") "Der kanonische Store wurde noch nicht initialisiert." else if (model$status == "empty") "Der kanonische Store ist leer und für die Vorschau bereit." else "Die erste fachliche Historie ist verfügbar."
    ))
    model
  }
  choice_vector <- function(rows) {
    if (!length(rows)) return(c("Bitte wählen" = ""))
    labels <- vapply(rows, function(row) {
      label <- if (!is.null(row$selection_label)) row$selection_label else row$label
      data_cash_account_label_v1(label, row$account_type)
    }, character(1L))
    c("Bitte wählen" = "", stats::setNames(vapply(rows, `[[`, character(1L), "ref"), labels))
  }
  multi_choice_vector <- function(rows) {
    if (!length(rows)) return(stats::setNames(character(), character()))
    labels <- vapply(rows, function(row) {
      label <- if (!is.null(row$selection_label)) row$selection_label else row$label
      data_cash_account_label_v1(label, row$account_type)
    }, character(1L))
    stats::setNames(vapply(rows, `[[`, character(1L), "ref"), labels)
  }
  refresh_transaction_catalog <- function() {
    model <- data_transaction_editor_refresh_v1(transaction_editor, runtime$context)
    transaction_catalog(model)
    shiny::updateSelectInput(session, "transaction_portfolio", choices = choice_vector(model$portfolios))
    shiny::updateSelectInput(session, "transaction_account", choices = choice_vector(model$accounts))
    shiny::updateSelectInput(session, "transaction_cash_account", choices = choice_vector(model$accounts))
    shiny::updateSelectInput(session, "transaction_counterparty", choices = choice_vector(model$accounts))
    shiny::updateSelectInput(session, "transaction_destination", choices = choice_vector(model$accounts))
    shiny::updateSelectInput(session, "transaction_asset", choices = choice_vector(model$assets))
    shiny::updateSelectInput(session, "transaction_cash_asset", choices = choice_vector(model$assets))
    shiny::updateSelectInput(session, "transaction_current", choices = choice_vector(model$current_transactions))
    model
  }
  transaction_form <- function() list(
    action = input$transaction_action, profile = input$transaction_profile, portfolio_ref = input$transaction_portfolio,
    transaction_ref = input$transaction_current, effective_at_utc = input$transaction_effective, local_date = input$transaction_date,
    account_ref = input$transaction_account, asset_ref = input$transaction_asset, cash_account_ref = input$transaction_cash_account,
    cash_asset_ref = input$transaction_cash_asset, counterparty_account_ref = input$transaction_counterparty,
    destination_account_ref = input$transaction_destination, quantity_decimal = input$transaction_quantity,
    unit_price_decimal = input$transaction_price, amount_decimal = input$transaction_amount,
    fee_decimal = input$transaction_fee, tax_decimal = input$transaction_tax, memo = input$transaction_memo
  )
  # Echo-Schutz fuer das Asset im Formular (#511): Der Server setzt das Asset selbst, sobald die Suche
  # wechselt. Das Echo eines solchen Werts ist keine eigene Wahl im Formular und darf die Buchungsart nicht umstellen. Gemessen:
  # (1) Wechselt die Suche zweimal kurz hintereinander, kam das Echo der ersten Wahl nach der zweiten an. (2) Fuer das EUR-Cash-Asset,
  # das im Formular nicht waehlbar ist, setzt der Server ersatzweise das erste Asset der Liste; dessen Echo stellte die Buchungsart
  # auf Non-Cash zurueck. Gemerkt wird hoechstens zehn Sekunden; ein Echo verbraucht seinen Eintrag und alle aelteren.
  activity_asset_sent <- list()
  activity_asset_update <- function(...) {
    args <- list(...)
    if (is.character(args$selected) && length(args$selected) == 1L)
      activity_asset_sent <<- c(Filter(function(item) difftime(Sys.time(), item$at, units = "secs") < 10, activity_asset_sent),
                                list(list(value = args$selected, at = Sys.time())))
    do.call(shiny::updateSelectInput, c(list(session, "activity_asset"), args))
  }
  activity_asset_server_echo <- function(value) {
    kept <- Filter(function(item) difftime(Sys.time(), item$at, units = "secs") < 10, activity_asset_sent)
    values <- vapply(kept, function(item) item$value, character(1L))
    hit <- which(values == if (is.character(value) && length(value) == 1L) value else "")
    activity_asset_sent <<- if (length(hit)) kept[-seq_len(max(hit))] else kept
    length(hit) > 0L
  }
  # Der Asset-Center fuehrt Katalog-Editor-Refs, das Transaktionsformular
  # Activity-Editor-Refs. Beide zeigen auf dieselbe interne Identitaet.
  activity_ref_for_center <- function(kind, center_ref) {
    if (!is.character(center_ref) || length(center_ref) != 1L || is.na(center_ref) || !nzchar(center_ref)) return("")
    value <- tryCatch({
      internal <- desktop_catalog_editor_internal_identity_v1(
        asset_center_catalog_editor, runtime$context, kind, center_ref
      )
      data_asset_activity_editor_ref_for_internal_v1(activity_editor, runtime$context, kind, internal)
    }, error = function(error) NULL)
    if (is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value)) value else ""
  }
  # `reuse = TRUE` liest nichts neu: Ein Wechsel in der Suche aendert nichts auf
  # der Platte, nur das Ziel im Formular. Katalog und Activity-Sicht neu zu lesen
  # startet zwei Python-Teilprozesse und blockiert die Sitzung, bei grossen
  # Bestaenden mehrere Sekunden je Assetwechsel.
  # In der Marktdatenpflege liess genau diese Blockade den Server hinter dem
  # Browser herlaufen, und ein fertiger Bewertungsentwurf wurde von einem spaet
  # verarbeiteten Echo verworfen (#283). Nach jedem Schreibvorgang wird weiterhin
  # voll gelesen.
  # Stand der Stammdaten, mit dem die Maske zuletzt gelesen hat (#452): Beim Oeffnen des Reiters "Transaktionen" wird nur neu
  # gelesen, wenn sich canonical.sqlite seither geaendert hat - etwa nach einem neuen Asset oder Konto. Das ersetzt den Knopf
  # "Asset-Auswahl und Historie aktualisieren"; nach eigenen Buchungen liest jede Karte ohnehin selbst neu.
  canonical_stamp <- function() tryCatch({
    path <- file.path(runtime_data_space_path(runtime$context), "canonical.sqlite")
    info <- file.info(c(path, paste0(path, "-wal")))
    paste(info$size, as.numeric(info$mtime), collapse = "|")
  }, error = function(error) NA_character_)
  activity_catalog_stamp <- NA_character_
  refresh_activity_catalog <- function(force_context = FALSE, reuse = FALSE) {
    model <- if (isTRUE(reuse) && !is.null(activity_read_view())) activity_catalog() else NULL
    if (is.null(model)) {
      stamp <- canonical_stamp()
      activity_read_view(data_asset_activity_editor_read_view_v1(activity_editor, runtime$context))
      model <- data_asset_activity_editor_refresh_v1(activity_editor, runtime$context); activity_catalog(model)
      activity_catalog_stamp <<- stamp
    }
    asset_refs <- if (length(model$assets)) vapply(model$assets, `[[`, character(1L), "ref") else character()
    account_refs <- if (length(model$accounts)) vapply(model$accounts, `[[`, character(1L), "ref") else character()
    portfolio_refs <- if (length(model$portfolios)) vapply(model$portfolios, `[[`, character(1L), "ref") else character()
    retain_one <- function(value, refs=asset_refs) {
      if (is.character(value) && length(value) == 1L && !is.na(value) && value %in% refs) value else ""
    }
    last_context <- activity_last_successful_context()
    retained_target <- retain_one(input$activity_asset)
    center_asset_ref <- asset_center_selected_ref
    center_target <- retain_one(activity_ref_for_center("asset", center_asset_ref))
    center_portfolio <- retain_one(activity_ref_for_center("portfolio", asset_center_selected_portfolio_ref), portfolio_refs)
    # Das Asset-Center fuehrt den Arbeitskontext: Eine dort getroffene Auswahl
    # setzt sich im Formular durch, damit ein Assetwechsel auch die abhaengigen
    # Tabellen umstellt.
    #
    # Gesperrt wird der Wechsel nur bei eingegebenen Betraegen oder einer aktiven
    # Buchungsauswahl. Nicht anhand von workflow$dirty: Portfolio, Konto und
    # Asset werden hier selbst vorbelegt, wodurch das Formular sofort von seiner
    # Baseline abweicht und als "Entwurf begonnen" gaelte - der Wechsel kaeme nie
    # durch. Die Zielauswahl ist Kontext, nicht eingegebener Inhalt; geschuetzt
    # gehoeren die Werte.
    # Dieselbe Regel wie im Formular: Ein ausgeblendetes Betragsfeld der anderen
    # Betragsart ist keine Eingabe und sperrt den Kontext nicht.
    visible_amounts <- desktop_product_activity_amount_fields_v1(input$activity_amount_mode, input$activity_unit_price, input$activity_gross_total)
    net_mode <- identical(input$activity_type, "dividend") && isTRUE(input$activity_amount_mode %in% desktop_product_activity_net_amount_modes_v1())
    entered_amount <- any(vapply(
      list(input$activity_quantity, visible_amounts$unit_price_decimal, visible_amounts$gross_amount_decimal,
           if (net_mode && identical(input$activity_amount_mode, "net_total")) input$activity_net_total else "",
           if (net_mode && identical(input$activity_amount_mode, "net_quantity_unit_price")) input$activity_net_unit_price else "",
           input$activity_monetary_fee, input$activity_asset_fee,
           input$activity_eligible_quantity, input$activity_provided_basis),
      function(value) is.character(value) && length(value) == 1L && !is.na(value) && nzchar(trimws(value)),
      logical(1L)
    ))
    selection_active <- length(workflow_refs()) > 0L
    # force_context nutzt nur "Eingaben verwerfen": Die Betragsfelder werden per
    # updateTextInput geleert, was erst nach einem Browser-Roundtrip in input$
    # ankommt. Ohne Erzwingen hielte die Sperre im selben Durchlauf noch an den
    # alten Betraegen fest. Eine aktive Buchungsauswahl bleibt davon unberuehrt.
    context_locked <- selection_active || (entered_amount && !isTRUE(force_context))
    if (nzchar(center_target) && context_locked && !identical(center_target, retained_target)) {
      activity_context_block(if (selection_active)
        "Asset-Wechsel nicht übernommen: Eine Buchung ist ausgewählt. Zum Wechseln die Buchungsauswahl leeren."
      else
        "Asset-Wechsel nicht übernommen: Im Formular sind Beträge eingegeben. „Eingaben verwerfen“ gibt den Wechsel frei.")
    } else {
      activity_context_block(NULL)
    }
    if (nzchar(center_target) && !context_locked) retained_target <- center_target
    if (!nzchar(retained_target)) retained_target <- center_target
    # Die Asset-Historie folgt dem Analyse-Scope, nicht dem Formularfeld. Dieser
    # Scope ist vertraglich ausdruecklich: test_data_asset_center_product_flow_v1
    # verlangt, dass er nach einem Aktualisieren leer bleibt. Nur der Handoff
    # darf ihn setzen, weil das eine ausdrueckliche Nutzeraktion ist. Eine
    # automatische Eingrenzung der Historie braucht daher eine eigene
    # Entscheidung und ist hier bewusst nicht umgesetzt.
    retained_portfolio <- retain_one(input$activity_portfolio,portfolio_refs)
    if (nzchar(center_portfolio) && !context_locked) retained_portfolio <- center_portfolio
    if (!nzchar(retained_portfolio)) retained_portfolio <- center_portfolio
    if (!nzchar(retained_portfolio) && is.list(last_context)) retained_portfolio <- retain_one(last_context$portfolio_ref,portfolio_refs)
    # With a single portfolio there is nothing to choose (#391).
    if (!nzchar(retained_portfolio) && length(portfolio_refs) == 1L) retained_portfolio <- portfolio_refs[[1L]]
    # Das Konto der jeweils juengsten Buchung. `target = ""` fragt ueber alle
    # Assets - die Vorbelegung soll auch bei einem Asset ohne eigene Buchung aus
    # dem zuletzt verwendeten Konto kommen und nicht leer bleiben (#424).
    asset_latest_account <- function(target) {
      view <- tryCatch(activity_read_view(), error = function(error) NULL)
      projection <- tryCatch(if (is.null(view)) NULL else
        asset_selection_context_project_activity_v3(model, view, scope_mode = "all"), error = function(error) NULL)
      if (is.null(projection)) return("")
      for (portfolio in projection$portfolios) for (row in portfolio$events_newest_first) {
        if ((!nzchar(target) || identical(row$asset_ref, target)) &&
            is.character(row$account_ref) && length(row$account_ref) == 1L) return(row$account_ref)
      }
      ""
    }
    asset_switched <- nzchar(retained_target) && !identical(retained_target, retain_one(input$activity_asset))
    retained_account <- if (asset_switched) "" else retain_one(input$activity_account,account_refs)
    if (!nzchar(retained_account)) retained_account <- retain_one(asset_latest_account(retained_target),account_refs)
    if (!nzchar(retained_account) && is.list(last_context)) retained_account <- retain_one(last_context$account_ref,account_refs)
    if (!nzchar(retained_account)) retained_account <- retain_one(asset_latest_account(""),account_refs)
    compatible_accounts <- .data_asset_activity_account_choice_state_v1(
      model, retained_portfolio, retained_target, retained_account,
      retain_one(input$activity_related_account,account_refs)
    )
    compatible_account <- compatible_accounts$account_ref
    retained_scope <- intersect(activity_scope_selected(), asset_refs)
    retained_excluded <- intersect(activity_scope_excluded(), asset_refs)
    retained_accounts <- intersect(activity_scope_accounts(), account_refs)
    activity_scope_selected(retained_scope)
    activity_scope_excluded(retained_excluded)
    activity_scope_accounts(retained_accounts)
    shiny::updateSelectInput(session, "activity_portfolio", choices=choice_vector(model$portfolios), selected=retained_portfolio)
    shiny::updateSelectInput(session, "activity_account", choices=choice_vector(model$accounts), selected=compatible_account)
    shiny::updateSelectInput(session, "activity_related_account", choices=choice_vector(model$accounts), selected=compatible_accounts$related_account_ref)
    activity_asset_update(choices=choice_vector(model$assets), selected=retained_target)
    shiny::updateSelectInput(session, "activity_source_asset", choices=choice_vector(model$assets), selected=retain_one(input$activity_source_asset))
    shiny::updateSelectizeInput(
      session, "activity_scope_assets", choices=multi_choice_vector(model$assets),
      selected=retained_scope, server=TRUE
    )
    shiny::updateSelectizeInput(
      session, "activity_scope_excluded_assets", choices=multi_choice_vector(model$assets),
      selected=retained_excluded, server=TRUE
    )
    shiny::updateSelectizeInput(
      session, "activity_scope_accounts", choices=multi_choice_vector(model$accounts),
      selected=retained_accounts, server=TRUE
    )
    completion_selected<-input$portfolio_completion_assets
    if(is.null(completion_selected))completion_selected<-character()
    shiny::updateSelectizeInput(session,"portfolio_completion_assets",choices=multi_choice_vector(model$assets),selected=intersect(completion_selected,asset_refs),server=TRUE)
    shiny::updateRadioButtons(session, "activity_scope_mode", selected=activity_scope_view_mode())
    quick_portfolio <- if(length(model$portfolios)) model$portfolios[[1L]]$ref else ""
    quick_asset <- if(length(model$assets)) model$assets[[1L]]$ref else ""
    quick_compatible <- .data_asset_activity_account_choice_state_v1(model,quick_portfolio,quick_asset,"","")$accounts
    quick_account <- if(length(quick_compatible)) quick_compatible[[1L]]$ref else ""
    shiny::updateSelectInput(session,"activity_quick_portfolio",choices=choice_vector(model$portfolios),selected=quick_portfolio)
    shiny::updateSelectInput(session,"activity_quick_asset",choices=choice_vector(model$assets),selected=quick_asset)
    shiny::updateSelectInput(session,"activity_quick_default_account",choices=choice_vector(model$accounts),selected=quick_account)
    model
  }
  activity_position_after_write <- function(form) {
    projection <- tryCatch({
      catalog <- activity_catalog(); view <- activity_read_view()
      if (is.null(catalog) || is.null(view)) NULL else data_asset_activity_context_projection_v1(
        catalog, asset_selection_context_project_activity_v3(catalog, view, scope_mode='all'),
        form$portfolio_ref, form$asset_ref, form$account_ref
      )
    }, error=function(error) NULL)
    if (is.null(projection) || !identical(projection$status, 'ready')) return(NULL)
    rows <- unlist(lapply(projection$portfolios, function(portfolio) portfolio$positions), recursive=FALSE)
    if (length(rows) != 1L) return(NULL)
    row <- rows[[1L]]
    # Deutsch formatiert wie die Buchungstabelle (0.3.4, #578); mit „Exakte Brüche anzeigen“ die Werte des Kerns.
    parts <- c(
      paste("Bestand", if (isTRUE(input$activity_show_exact_ratios)) row$remaining_quantity_decimal else pl_quantity_v1(row$remaining_quantity_decimal)),
      paste("Einstandswert", activity_money(row$remaining_fifo_basis, row$currency))
    )
    if (!is.null(row$cost_average)) {
      parts <- c(parts, paste("Ø Einstandskurs", activity_price(row$cost_average, row$currency)))
    }
    paste(parts, collapse=" · ")
  }
  activity_context_projection <- shiny::reactive({
    if (length(workflow_refs())>1L) return(list(status='selection_required',portfolios=list()))
    catalog <- activity_catalog(); view <- activity_read_view()
    projection <- tryCatch(if(is.null(catalog)||is.null(view))NULL else
      asset_selection_context_project_activity_v3(catalog,view,scope_mode='all'),error=function(error)NULL)
    data_asset_activity_context_projection_v1(catalog,projection,input$activity_portfolio,input$activity_asset,input$activity_account)
  })
  output$activity_context_state <- shiny::renderUI({
    value <- activity_context_projection()
    copy <- switch(value$status,ready='Abgeschlossener frischer FIFO-Stand für das Formularziel.',
      empty='Im frischen Stand sind für dieses Formularziel keine Positionen vorhanden.',
      selection_required='Portfolio und Asset im Formular wählen. Keine gemeinsame Kontrolle für Mehrfachauswahl.',
      blocked='Formularziel nicht eindeutig oder Konto gehört nicht zum Portfolio.',
      'Bestandskontrolle nicht verfügbar: frischer FIFO-Stand oder eindeutige Portfolioevidenz fehlt. Das ist kein Nullbestand.')
    portelyra_status_panel('Bestandskontrolle zum Formular',copy,tone=if(value$status %in% c('ready','empty'))'neutral'else'warning')
  })
  activity_selection_projection <- shiny::reactive({
    catalog <- activity_catalog(); view <- activity_read_view()
    if (is.null(catalog) || is.null(view)) return(NULL)
    scalar_input <- function(value, fallback) {
      if (is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value)) value else fallback
    }
    domains <- activity_scope_domains()
    account_match <- scalar_input(activity_scope_account_match(), "any")
    account_usage <- scalar_input(activity_scope_account_usage(), "current")
    tryCatch(
      asset_selection_context_project_activity_v3(
        catalog, view,
        manual_asset_refs = activity_scope_selected(),
        scope_mode = activity_scope_view_mode(),
        excluded_asset_refs = activity_scope_excluded(),
        asset_domains = domains,
        account_refs = activity_scope_accounts(),
        account_match = account_match,
        account_usage = account_usage,
        interval_enabled = activity_scope_interval_enabled(),
        interval_from = activity_scope_interval_from(),
        interval_to = activity_scope_interval_to(),
        interval_relation = activity_scope_interval_relation(),
        holding_mode = activity_scope_holding_mode()
      ),
      spot_asset_selection_context_error = function(error) list(
        asset_selection_activity_projection_version = 3L,
        status = "blocked", error_code = error$code, unavailable_reason = NULL,
        scope_mode = activity_scope_view_mode(), fifo_state = view$fifo_state,
        supported_asset_domains = "noncash", requested_asset_domains = domains,
        account_filter_status = "unavailable", account_match = account_match,
        account_usage = account_usage, selected_account_count = as.integer(length(activity_scope_accounts())),
        interval_filter_status = "unavailable",
        interval_enabled = activity_scope_interval_enabled(),
        interval_from = activity_scope_interval_from(), interval_to = activity_scope_interval_to(),
        interval_relation = activity_scope_interval_relation(), holding_mode = activity_scope_holding_mode(),
        holding_evidence_status = "unavailable", activity_interval_asset_count = 0L,
        holding_interval_asset_count = 0L, interval_filter_asset_count = 0L,
        opening_context_event_count = 0L,
        available_asset_count = as.integer(length(catalog$assets)),
        manual_asset_count = as.integer(length(activity_scope_selected())),
        filter_asset_count = 0L, excluded_asset_count = as.integer(length(activity_scope_excluded())),
        resolved_asset_count = 0L, visible_position_count = 0L,
        visible_custody_position_count = 0L, visible_event_count = 0L,
        manual_assets = list(), filter_assets = list(), excluded_assets = list(),
        resolved_assets = list(), selected_accounts = list(), portfolios = list(),
        browser_local = TRUE, calculation_started = FALSE,
        provider_access = FALSE, network_access = FALSE, canonical_write = FALSE,
        path_exposed = FALSE, internal_id_exposed = FALSE
      )
    )
  })
  activity_quick_mapping_entries <- function(kind) {
    inspection<-activity_quick_inspection();if(is.null(inspection)||!is.list(inspection$mapping_requirements))return(list())
    requirements<-inspection$mapping_requirements[[kind]];if(!length(requirements))return(list())
    singular<-switch(kind,portfolios="portfolio",accounts="account",assets="asset",stop("data_activity_quick_import_mapping_required",call.=FALSE))
    lapply(seq_along(requirements),function(index)list(source_key=requirements[[index]]$source_key,target_ref=input[[sprintf("activity_quick_map_%s_%03d",singular,index)]]))
  }
  refresh_activity_quick_profiles <- function() {
    model<-data_activity_quick_mapping_profiles_v1(activity_quick_center,runtime$context);activity_quick_profiles(model)
    choices<-if(length(model$profiles))stats::setNames(vapply(model$profiles,`[[`,character(1L),"profile_handle"),vapply(model$profiles,function(row)paste(if(isTRUE(row$is_standard))"Standard ·"else"Profil ·",row$profile_label,"· Fassung",row$revision),character(1L)))else c("Keine gespeicherten Profile"="")
    standard<-Filter(function(row)isTRUE(row$is_standard),model$profiles);selected<-if(length(standard))standard[[1L]]$profile_handle else if(length(model$profiles))model$profiles[[1L]]$profile_handle else ""
    shiny::updateSelectInput(session,"activity_quick_profile_select",choices=choices,selected=selected);model
  }
  apply_activity_quick_profile <- function(loaded) {
    profile<-loaded$profile;inspection<-activity_quick_inspection()
    shiny::updateSelectInput(session,"activity_quick_portfolio",selected=profile$default_portfolio_ref)
    shiny::updateSelectInput(session,"activity_quick_default_account",selected=profile$default_account_ref)
    if(!is.null(inspection)&&is.list(inspection$mapping_requirements))for(kind in c("portfolios","accounts","assets")){
      singular<-switch(kind,portfolios="portfolio",accounts="account",assets="asset")
      mappings<-profile[[paste0(sub("s$","",kind),"_mappings")]]
      if(identical(kind,"portfolios"))mappings<-profile$portfolio_mappings
      if(identical(kind,"accounts"))mappings<-profile$account_mappings
      if(identical(kind,"assets"))mappings<-profile$asset_mappings
      by_key<-setNames(mappings,vapply(mappings,`[[`,character(1L),"source_key"))
      requirements<-inspection$mapping_requirements[[kind]]
      for(index in seq_along(requirements)){
        entry<-by_key[[requirements[[index]]$source_key]]
        shiny::updateSelectInput(session,sprintf("activity_quick_map_%s_%03d",singular,index),selected=if(is.null(entry))""else entry$target_ref)
      }
    }
    activity_quick_loaded_profile(loaded);loaded
  }
  refresh_activity_drafts <- function() {
    model<-data_activity_draft_refresh_v1(activity_draft_center,runtime$context,open_only=TRUE);activity_draft_list(model);activity_draft_reasons(list())
    open_rows<-model$drafts
    choices<-if(length(open_rows))stats::setNames(vapply(open_rows,`[[`,character(1L),"draft_handle"),vapply(seq_along(open_rows),function(index){row<-open_rows[[index]];event_type<-row$event_summary$event_type;if(is.null(event_type)||!is.character(event_type)||length(event_type)!=1L||is.na(event_type)||!nzchar(event_type))event_type<-"ohne event_type";if(!is.null(row$selected_event_count))event_type<-paste(row$selected_event_count,'Buchungen gemeinsam stornieren');paste0(index," · ",row$status," · ",row$origin_type," · ",event_type)},character(1L)))else c("Keine offenen Entwürfe"="")
    current<-shiny::isolate(input$activity_draft_select)
    selected<-if(length(current)==1L&&current%in%unname(choices))current else ''
    if(length(open_rows))choices<-c('Bitte wählen'='',choices)
    activity_draft_approval(NULL);shiny::updateCheckboxInput(session,'activity_draft_confirm',value=FALSE)
    shiny::updateSelectInput(session,"activity_draft_select",choices=choices,selected=selected)
    if(nzchar(selected)){
      opened<-data_activity_draft_open_v1(activity_draft_center,activity_editor,runtime$context,selected);activity_draft_open(opened)
      fields<-unique(c(intersect(opened$missing_fields,.data_activity_draft_editable_fields_v1()),.data_activity_draft_editable_fields_v1()));shiny::updateSelectInput(session,"activity_draft_field",choices=stats::setNames(fields,fields),selected=fields[[1L]])
    }else activity_draft_open(activity_draft_completed())
    model
  }
  # Der Stapel haengt allein am Quell-Fingerprint, nicht an der Datei. Wird er
  # ausdruecklich uebergeben, laesst sich ein abgebrochener Lauf ohne erneute
  # Dateivorlage fortsetzen (#422).
  refresh_statement_reward_valuations <- function(progress_callback=NULL,source_fingerprint=NULL) {
    if(is.null(source_fingerprint)){
      preview<-statement_exchange_preview()
      source_fingerprint<-if(!is.null(preview)&&!is.null(preview$source_fingerprint))preview$source_fingerprint else statement_batch_source()
      if(is.null(source_fingerprint))stop("statement_reward_valuation_preview_required",call.=FALSE)
    }
    statement_batch_source(source_fingerprint)
    if(is.null(activity_catalog()))invisible(refresh_activity_catalog())
    batch<-data_activity_draft_reward_batch_v1(activity_draft_center,activity_editor,runtime$context,source_fingerprint,progress_callback)
    statement_reward_valuation_batch(batch);catalog<-activity_catalog()
    label_for<-function(rows,ref){matches<-Filter(function(row)identical(row$ref,ref),rows);if(length(matches)==1L)matches[[1L]]$label else "Unbekannt"}
    choices<-if(length(batch$drafts))stats::setNames(vapply(batch$drafts,`[[`,character(1L),"draft_handle"),vapply(batch$drafts,function(row)paste("Zeile",row$source_row_ordinal,"·",row$event_summary$local_date,"·",label_for(catalog$assets,row$asset_ref),"·",row$valuation_summary$lifecycle),character(1L)))else c("Keine Reward-Entwürfe für diesen Auszug"="")
    pending<-Filter(function(row)identical(row$valuation_summary$lifecycle,"valuation_pending"),batch$drafts);selected<-if(length(pending))pending[[1L]]$draft_handle else if(length(batch$drafts))batch$drafts[[1L]]$draft_handle else ""
    shiny::updateSelectInput(session,"statement_reward_valuation_select",choices=choices,selected=selected)
    statement_reward_valuation_open(if(nzchar(selected))data_activity_draft_open_v1(activity_draft_center,activity_editor,runtime$context,selected)else NULL)
    batch
  }
  refresh_activity_event_choices <- function() {
    event_type <- input$activity_type
    if (is.null(event_type) || !nzchar(event_type)) return(invisible(NULL))
    policy <- desktop_product_activity_event_policy_v1(event_type)
    loading <- if(is.null(activity_workflow_loading))NULL else activity_workflow_loading$form
    amount_labels <- c(quantity_unit_price="Menge × Stückpreis", gross_total="Brutto-Gesamtbetrag", not_applicable="Nicht anwendbar",
      net_total="Netto-Gesamtbetrag → Brutto", net_quantity_unit_price="Menge × Netto-Stückpreis → Brutto")
    amount_choices <- desktop_product_activity_amount_mode_choices_v1(event_type)
    # Eine Wahl, die zum Ereignis passt, bleibt stehen; der Standard gilt nur, wenn
    # sie nicht passt. Beim Laden einer Buchung meldet der Browser Ereignis und
    # Betragsart in einem Schub. Der Abgleich erkennt die Buchung daran als geladen
    # und hebt die Ladevorlage auf - und laeuft dieser Beobachter erst danach,
    # stellte er die eben geladene Betragsart auf den Standard zurueck: Eine als
    # Brutto-Gesamtbetrag gebuchte Dividende stand dann als "Menge x Stueckpreis"
    # mit leerem Preis in der Maske, und die Korrektur wurde abgelehnt (im Browser
    # nachgestellt).
    behalten <- function(value, allowed) is.character(value) && length(value) == 1L && !is.na(value) && value %in% allowed
    amount_mode <- if(!is.null(loading) && loading$amount_input_mode %in% policy$amount_modes) loading$amount_input_mode
      else if(behalten(input$activity_amount_mode, amount_choices)) input$activity_amount_mode else policy$default_amount_mode
    basis_mode <- if(!is.null(loading) && loading$basis_evidence_mode %in% policy$basis_modes) loading$basis_evidence_mode
      else if(behalten(input$activity_basis_mode, policy$basis_modes)) input$activity_basis_mode else policy$default_basis_mode
    basis_labels <- c(derived_trade="Trade abgeleitet", valuation_confirmed_as_basis="Bewertung als Basis bestätigt", provided_basis="Basis explizit belegt", basis_missing="Basis fehlt", not_applicable="Nicht anwendbar")
    shiny::updateSelectInput(
      session, "activity_amount_mode", choices=stats::setNames(amount_choices, amount_labels[amount_choices]),
      selected=amount_mode
    )
    shiny::updateSelectInput(
      session, "activity_basis_mode", choices=stats::setNames(policy$basis_modes, basis_labels[policy$basis_modes]),
      selected=basis_mode
    )
    invisible(NULL)
  }
  refresh_activity_account_choices <- function() {
    model <- activity_catalog()
    if (is.null(model)) return(invisible(NULL))
    loading <- if(is.null(activity_workflow_loading))NULL else activity_workflow_loading$form
    asset <- if(is.null(loading))input$activity_asset else loading$asset_ref
    portfolio <- if(is.null(loading))input$activity_portfolio else loading$portfolio_ref
    account <- if(is.null(loading))input$activity_account else loading$account_ref
    related <- if(is.null(loading))input$activity_related_account else loading$related_account_ref
    event_type <- if(is.null(loading))input$activity_type else loading$event_type
    selected_asset <- Filter(function(value) identical(value$ref, asset), model$assets)
    choices <- .data_asset_activity_account_choice_state_v1(
      model, portfolio, asset, account, related
    )
    shiny::updateSelectInput(
      session, "activity_account", choices=choice_vector(choices$accounts), selected=choices$account_ref
    )
    shiny::updateSelectInput(
      session, "activity_related_account", choices=choice_vector(choices$accounts), selected=if(identical(event_type,"transfer"))choices$related_account_ref else ""
    )
    if (length(selected_asset) == 1L && identical(input$activity_type, "reward") &&
        !identical(selected_asset[[1L]]$asset_type, "crypto")) {
      state(list(tone="error", title="Auswahl der Buchung blockiert", copy=pl_error_text_v1("data_asset_activity_editor_selection_invalid")))
    }
    invisible(NULL)
  }
  optional_date <- function(value) if (inherits(value, "Date") && length(value)==1L && !is.na(value)) value else ""
  # Jedes Betragsfeld der Buchungsmaske darf leer sein oder einen Wert groesser
  # null tragen - eine eingetippte 0 lehnt der Kern ab. Der Grund kam nie
  # an: aus asset_activity_amount_invalid wurde ueber drei Ebenen
  # erst schema400_asset_activity_input_invalid, dann
  # desktop_asset_activity_input_invalid und schliesslich
  # desktop_product_boundary_failed - "Aktion blockiert", ohne jeden Hinweis auf
  # die Gebuehr (#422).
  activity_amount_complaint <- function(form) {
    felder<-c(quantity_decimal="Menge",eligible_quantity_decimal="Anrechenbare Menge",
      unit_price_decimal="Stückpreis",gross_amount_decimal="Brutto-Gesamtbetrag",
      monetary_fee_decimal="Gebühr",asset_fee_quantity_decimal="Gebühr in Stücken",
      provided_basis_decimal="Belegte Basis")
    null_eingaben<-character()
    for(feld in names(felder)){
      wert<-form[[feld]]
      if(!is.character(wert)||length(wert)!=1L||is.na(wert)||!nzchar(wert))next
      if(grepl("^0+(\\.0+)?$",wert))null_eingaben<-c(null_eingaben,unname(felder[[feld]]))
    }
    if(!length(null_eingaben))return(NULL)
    if(length(null_eingaben)==1L)
      sprintf("%s darf nicht null sein. Lass das Feld leer, wenn der Betrag nicht angefallen ist.",null_eingaben)
    else
      sprintf("%s dürfen nicht null sein. Lass die Felder leer, wenn die Beträge nicht angefallen sind.",
        paste(null_eingaben,collapse=" und "))
  }
  activity_form_issues <- function(form) {
    issues<-character()
    present<-function(value)is.character(value)&&length(value)==1L&&!is.na(value)&&nzchar(value)
    if(!present(form$portfolio_ref))issues<-c(issues,"Portfolio")
    if(!present(form$account_ref))issues<-c(issues,"Quellkonto")
    if(!present(form$related_account_ref))issues<-c(issues,"Zielkonto")
    if(present(form$account_ref)&&identical(form$account_ref,form$related_account_ref))issues<-c(issues,"Quell- und Zielkonto müssen verschieden sein")
    if(!present(form$asset_ref))issues<-c(issues,"Asset")
    if(!inherits(form$local_date,"Date")||length(form$local_date)!=1L||is.na(form$local_date))issues<-c(issues,"Datum")
    if(!present(form$time_zone))issues<-c(issues,"Zeitzone")
    if(identical(form$event_time_evidence,"exact")&&(!present(form$local_time)||!grepl("^[0-9]{2}:[0-9]{2}:[0-9]{2}$",form$local_time)))issues<-c(issues,"Uhrzeit")
    quantity<-form$quantity_decimal
    if(!present(quantity)||!grepl("^(0|[1-9][0-9]*)(\\.[0-9]+)?$",quantity)||grepl("^0(?:\\.0+)?$",quantity))issues<-c(issues,"positive Menge mit Dezimalpunkt")
    if(!identical(form$amount_input_mode,"not_applicable"))issues<-c(issues,"Betragsmodus: Nicht anwendbar")
    if(!identical(form$basis_evidence_mode,"not_applicable"))issues<-c(issues,"Nachweis der Anschaffung: nicht anwendbar")
    if(!identical(form$original_acquired_time_evidence,"not_applicable"))issues<-c(issues,"ursprüngliche Anschaffungszeit: Nicht anwendbar")
    if(!identical(form$movement_context_code,"not_applicable"))issues<-c(issues,"Anlass: Nicht anwendbar")
    if(present(form$source_asset_ref)||any(vapply(list(form$eligible_quantity_decimal,form$unit_price_decimal,form$gross_amount_decimal,form$provided_basis_decimal),present,logical(1L))))issues<-c(issues,"nicht anwendbare Zusatzfelder leeren")
    unique(issues)
  }
  # Die Umrechnung der Netto-Betragsarten; NULL, wenn keine davon gewaehlt ist.
  activity_net_gross <- function() {
    if (!identical(input$activity_type, "dividend") || !isTRUE(input$activity_amount_mode %in% desktop_product_activity_net_amount_modes_v1())) return(NULL)
    if (identical(input$activity_amount_mode, "net_total")) data_net_amount_gross_v1(input$activity_net_total, input$activity_net_tax_rate)
    else data_net_amount_gross_v1(input$activity_net_unit_price, input$activity_net_tax_rate,
      quantity_decimal = if (is.null(input$activity_eligible_quantity)) "" else input$activity_eligible_quantity)
  }
  output$activity_net_gross_hint <- shiny::renderText({
    net <- activity_net_gross()
    if (is.null(net)) "" else data_net_amount_gross_hint_v1(net)
  })
  activity_form <- function() {
    event <- desktop_product_activity_event_form_v1(input$activity_type,
      desktop_product_activity_core_amount_mode_v1(input$activity_type, input$activity_amount_mode), input$activity_basis_mode)
    # Was der Kern bei dieser Buchungsart nicht liest, geht leer bzw. als "nicht anwendbar" mit (#422) - die Maske blendet
    # es aus, im Browser behaelt es aber seinen Wert.
    takes <- activity_takes()
    time <- desktop_product_activity_time_form_v1(
      input$activity_time_evidence, optional_date(input$activity_date), input$activity_time,
      input$activity_zone, input$activity_utc, if (takes("acquisition")) input$activity_acquisition_evidence else "not_applicable",
      optional_date(input$activity_acquisition_date), input$activity_acquisition_time,
      input$activity_acquisition_zone, input$activity_acquisition_utc
    )
    # Nur das Betragsfeld der gewaehlten Betragsart zaehlt; das ausgeblendete
    # andere behaelt im Browser seinen Wert, geht aber nicht ins Formular.
    amounts <- desktop_product_activity_amount_fields_v1(event$amount_input_mode,
      desktop_product_manual_decimal_v1(input$activity_unit_price), desktop_product_manual_decimal_v1(input$activity_gross_total))
    # Netto eingetragen: Der Bruttobetrag kommt aus der Umrechnung. Solange sie
    # nicht aufgeht, bleibt er leer - dann fehlt dem Formular sichtbar ein Betrag,
    # statt dass ein alter Brutto-Wert aus dem ausgeblendeten Feld gebucht wuerde.
    net <- activity_net_gross()
    if (!is.null(net)) amounts <- list(unit_price_decimal="", gross_amount_decimal=if (identical(net$status, "ready")) net$gross_amount_decimal else "")
    list(
      event_type=input$activity_type, portfolio_ref=input$activity_portfolio,
      account_ref=input$activity_account, related_account_ref=if (takes("related_account")) input$activity_related_account else "",
      asset_ref=input$activity_asset, source_asset_ref=if (takes("source_asset")) input$activity_source_asset else "",
      event_time_evidence=time$event_time_evidence, local_date=time$local_date,
      local_time=time$local_time, time_zone=time$time_zone, effective_at_utc=time$effective_at_utc,
      original_acquired_time_evidence=time$original_acquired_time_evidence,
      original_acquired_local_date=time$original_acquired_local_date,
      original_acquired_local_time=time$original_acquired_local_time,
      original_acquired_time_zone=time$original_acquired_time_zone,
      original_acquired_at_utc=time$original_acquired_at_utc,
      amount_input_mode=event$amount_input_mode, basis_evidence_mode=event$basis_evidence_mode,
      quantity_decimal=if(takes("quantity"))desktop_product_manual_decimal_v1(input$activity_quantity)else "",
      eligible_quantity_decimal=if(takes("eligible_quantity"))desktop_product_manual_decimal_v1(input$activity_eligible_quantity)else "",
      unit_price_decimal=amounts$unit_price_decimal, gross_amount_decimal=amounts$gross_amount_decimal,
      monetary_fee_decimal=if(takes("monetary_fee"))desktop_product_manual_decimal_v1(input$activity_monetary_fee)else "",
      asset_fee_quantity_decimal=if(takes("asset_fee"))desktop_product_manual_decimal_v1(input$activity_asset_fee)else "",
      provided_basis_decimal=if(takes("provided_basis"))desktop_product_manual_decimal_v1(input$activity_provided_basis)else "",
      movement_context_code=if(takes("movement_context"))input$activity_movement_context else "not_applicable"
    )
  }
  # Die Felder, die der Kern bei der gewaehlten Buchungsart liest; ohne gewaehlte Buchungsart keines.
  activity_takes <- function() {
    type <- input$activity_type
    fields <- if (is.character(type) && length(type) == 1L && type %in% DESKTOP_ACTIVITY_EVENT_TYPES)
      desktop_product_activity_relevant_fields_v1(type, input$activity_amount_mode, input$activity_basis_mode) else character()
    function(field) field %in% fields
  }
  # Pflichtangaben, die der Kern sonst nur mit einem Sammelcode ablehnt: Anlass und urspruengliche Anschaffungszeit bei Ein-
  # und Auslieferung.
  activity_required_complaint <- function(form) {
    takes <- activity_takes()
    if (takes("movement_context") && !isTRUE(form$movement_context_code %in% c("unclassified", "gift", "inheritance",
        "debt_settlement", "donation", "payment", "custody_exit", "other")))
      return("Bei einer Ein- oder Auslieferung den Anlass wählen, notfalls „Unklassifiziert“.")
    if (takes("acquisition") && identical(form$original_acquired_time_evidence, "not_applicable"))
      return("Bei einer Einlieferung die ursprüngliche Anschaffungszeit angeben: „Nur Datum“ oder „Exakt“, dazu Datum und Zeitzone.")
    desktop_product_activity_combination_complaint_v1(form$event_type, form$amount_input_mode, form$basis_evidence_mode)
  }
  # Die Auswahl kommt aus der Tabelle, nicht mehr aus einem Dropdown (#424).
  #
  # Laeuft ein Durchgang, fuehrt die Reihe die Auswahl serverseitig: genau die
  # Buchung, an der sie steht. Die Zeilenschluessel tragen die Generation und
  # wechseln bei jedem Schreibvorgang; die Kaestchen im Browser zeigen dann noch
  # auf die vorherige Generation. Deshalb wird in einem Durchgang nicht gelesen,
  # was der Browser meldet, sondern was die Reihe bestimmt.
  workflow_refs <- function() {
    if (!is.null(activity_sequence())) return(activity_sequence_ref())
    refs <- input$activity_rows_selected
    refs <- if (is.null(refs)) character() else sort(as.character(refs[nzchar(as.character(refs))]))
    # Veraltete Zeilenschluessel fallen nicht von selbst weg: Aendert sich die
    # Liste aus einem anderen Grund, soll die Auswahl nicht stillschweigend in
    # eine Neuanlage umschlagen. Freigegeben wird nur, was der Server nach einer
    # eigenen, geschriebenen Korrektur selbst freigegeben hat - bis rc.233 blieb
    # auch das stehen, die Maske war dann ausgeblendet, und zurueck fuehrte nur
    # "Auswahl leeren". Jetzt geschieht das automatisch.
    if (length(refs) && identical(refs, activity_rows_released())) character() else refs
  }
  # Die Spalten der Buchungstabelle. Bewusst wenige: Datum, Art, Konto, Menge,
  # Betrag, Gebuehr. Alles Weitere steht in der vollstaendigen Historie.
  # Angezeigt deutsch (#529 Punkt 8), gefiltert auf den exakten Werten.
  activity_rows_money <- function(values, frame) pl_amount_v1(values, if ("Waehrung" %in% names(frame)) frame$Waehrung else "", 2L, "—")
  activity_rows_columns <- function() list(
    data_table_workbench_column_v1("Datum","Datum",filter="date",format=function(values, frame) pl_day_v1(values, "—")),
    data_table_workbench_column_v1("Art","Art",filter="choice"),
    data_table_workbench_column_v1("Konto","Konto",filter="choice"),
    data_table_workbench_column_v1("Menge","Menge",filter="none",align="right",format=function(values, frame) pl_quantity_v1(values, "—")),
    data_table_workbench_column_v1("Betrag","Betrag",filter="number",align="right",format=activity_rows_money),
    data_table_workbench_column_v1("Gebuehr","Gebühr",filter="none",align="right",format=activity_rows_money),
    data_table_workbench_column_v1("Beleg","Beleg",filter="none"))
  # Die Belegangaben aller Buchungen, je Buchungsschluessel. Sie liegen neben dem
  # Buchungsbestand; gelesen wird mit der Liste und nach jedem Speichern. Laesst
  # sich der Speicher nicht lesen, bleibt die Tabelle benutzbar - der Bereich
  # darunter sagt es.
  activity_reference_model <- shiny::reactive({
    activity_reference_tick(); correction_model()
    tryCatch(activity_reference_service$read()$references,
      error=function(error) structure(list(), unreadable=TRUE))
  })
  # Der Buchungsschluessel je Zeile. Die Zeilenschluessel der Tabelle tragen die
  # Generation und wechseln bei jedem Schreibvorgang; die Belegangaben haengen an
  # der Buchung selbst. Die Zuordnung kennt nur der Server.
  activity_event_refs <- shiny::reactive({
    correction_model()
    tryCatch(data_asset_activity_correction_event_refs_v1(correction_center), error=function(error) character())
  })
  # Die eine gewaehlte Buchung, zu der Belegangaben erfasst werden. Mehrere
  # gewaehlte Zeilen oder ein laufender Durchgang: kein Eingabebereich.
  activity_reference_target <- shiny::reactive({
    refs <- workflow_refs()
    if (length(refs) != 1L || !is.null(activity_sequence())) return(NULL)
    ereignis <- unname(activity_event_refs()[refs[[1L]]])
    if (length(ereignis) != 1L || is.na(ereignis)) return(NULL)
    art <- tryCatch(unname(data_asset_activity_correction_event_types_v1(correction_center)[refs[[1L]]]), error=function(error) NA_character_)
    list(candidate_ref=refs[[1L]], event_ref=ereignis, event_type=if (length(art) == 1L && !is.na(art)) art else "")
  })
  # Der Wert eines Abgangs in EUR, wie ihn der Eigentuemer angibt - gelesen nur,
  # wenn ein Abgang gewaehlt ist. Ein Abgang traegt im Buchungsbestand keinen
  # Erloes; der Wert sagt, wieviel abgegangen ist, und aendert Bestand und FIFO nicht.
  activity_value_model <- shiny::reactive({
    activity_reference_tick(); correction_model()
    tryCatch(activity_reference_service$read_values()$values,
      error=function(error) structure(list(), unreadable=TRUE))
  })
  # Die Buchungen des in der Suche gewaehlten Assets. Die Suche steht ueber den
  # Reitern; ihr folgt die Tabelle, damit es nur eine Stelle gibt, die den
  # Kontext bestimmt - genau daran war die alte Oberflaeche gescheitert.
  #
  # Als reactive: Filter, Tabelle, Hinweis und Reihenstand lesen dieselbe Liste.
  # Als Funktion wurde sie je Ausgabe neu aus allen Buchungen gebildet - seit die
  # Liste beim Start von selbst laedt, viermal im ersten Durchlauf.
  activity_rows_frame <- shiny::reactive({
    model <- correction_model()
    if (is.null(model) || !is.list(model$candidates) || !length(model$candidates)) return(NULL)
    # Das Asset kommt aus der Suche des Asset-Centers. Dessen Referenzen gehoeren
    # zum Katalog-Editor, nicht zum Activity-Katalog - die beiden zu verwechseln
    # war genau der Fehler, der die falschen Zeilen zeigte. Aufgeloest wird darum ueber
    # data_asset_center_selected_v1 und verglichen ueber den Anzeigenamen, den auch
    # die Korrekturkandidaten tragen.
    gewaehlt <- tryCatch(input$asset_center_asset, error=function(error) NULL)
    label <- NULL
    if (is.character(gewaehlt) && length(gewaehlt)==1L && nzchar(gewaehlt)) {
      label <- tryCatch({
        katalog <- asset_center_catalog()
        treffer <- if (is.null(katalog)) NULL else data_asset_center_selected_v1(katalog, gewaehlt)
        if (is.null(treffer)) NULL else treffer$display_name
      }, error=function(error) NULL)
    }
    rows <- model$candidates
    # Passt kein Kandidat zum gewaehlten Asset, bleibt die Tabelle leer statt alle
    # Buchungen zu zeigen: "keine Buchung fuer dieses Asset" ist die Auskunft, die
    # gebraucht wird, nicht eine lange Liste fremder Zeilen.
    if (!is.null(label)) rows <- Filter(function(row) identical(row$asset_label, label), rows)
    art <- PL_EVENT_TYPE_LABELS_V1
    zahl <- function(value) if (is.null(value)||is.na(value)) NA_character_ else as.character(value)
    belege <- activity_reference_model(); ereignisse <- activity_event_refs()
        frame <- data.frame(
      Datum=vapply(rows,function(row)as.character(row$local_date),character(1L)),
      Art=vapply(rows,function(row){k<-as.character(row$event_type);if(k%in%names(art))unname(art[[k]])else k},character(1L)),
      Konto=vapply(rows,function(row)as.character(row$account_label),character(1L)),
      Menge=vapply(rows,function(row)zahl(row$quantity_decimal),character(1L)),
      Betrag=vapply(rows,function(row)zahl(row$gross_amount_decimal),character(1L)),
      Gebuehr=vapply(rows,function(row)zahl(row$monetary_fee_decimal),character(1L)),
      Waehrung=vapply(rows,function(row)if(is.null(row$currency))""else as.character(row$currency),character(1L)),
      Beleg=vapply(rows,function(row){ref<-unname(ereignisse[as.character(row$candidate_ref)]);if(length(ref)!=1L||is.na(ref))"—"else data_activity_reference_label_v1(belege[[ref]])},character(1L)),
      stringsAsFactors=FALSE, check.names=FALSE)
    schluessel <- vapply(rows,function(row)as.character(row$candidate_ref),character(1L))
    # Neueste zuerst.
    ordnung <- order(frame$Datum, decreasing=TRUE)
    list(frame=frame[ordnung,,drop=FALSE], keys=schluessel[ordnung], asset=label, total=length(model$candidates))
  })
  # --- Sammelbearbeitung mit "weiter" (#424) -------------------------------
  #
  # `candidate_ref` traegt die Generation der Buchung und wechselt darum bei jedem
  # Schreibvorgang. Eine Reihe ueber mehrere Buchungen kann sich daran nicht
  # festhalten. Sie merkt sich stattdessen die oeffentlichen Felder jeder Buchung
  # und ordnet die restlichen nach jedem Schritt neu zu. Gelingt das nicht
  # eindeutig, bricht die Reihe ab und sagt es - geraten wird nicht.
  .activity_sequence_text <- function(value) {
    if (is.null(value) || !length(value)) "" else as.character(value)[[1L]]
  }
  activity_sequence_key <- function(row) paste(
    vapply(c("portfolio_label","account_label","related_account_label","asset_label",
             "event_type","local_date","effective_at_utc","quantity_decimal",
             "gross_amount_decimal","monetary_fee_decimal"),
      function(field) .activity_sequence_text(row[[field]]), character(1L)),
    collapse = "\u001f")
  # Ordnet eine Folge von Schluesseln auf die aktuellen Kandidaten ab. Gleiche
  # Buchungen (etwa eine doppelt gebuchte Dividende) werden in der Reihenfolge der Kandidatenliste verbraucht, jede nur einmal.
  activity_sequence_resolve <- function(keys) {
    model <- correction_model()
    if (is.null(model) || !is.list(model$candidates) || !length(model$candidates)) return(NULL)
    vorrat <- model$candidates
    schluessel <- vapply(vorrat, activity_sequence_key, character(1L))
    genutzt <- rep(FALSE, length(vorrat))
    refs <- character(length(keys))
    for (i in seq_along(keys)) {
      treffer <- which(schluessel == keys[[i]] & !genutzt)
      if (!length(treffer)) return(NULL)
      genutzt[[treffer[[1L]]]] <- TRUE
      refs[[i]] <- as.character(vorrat[[treffer[[1L]]]]$candidate_ref)
    }
    refs
  }
  # Die Ref der Buchung, an der die Reihe gerade steht.
  activity_sequence_ref <- function() {
    reihe <- activity_sequence()
    if (is.null(reihe)) return(character())
    refs <- activity_sequence_resolve(reihe$keys[seq(reihe$index, length(reihe$keys))])
    if (is.null(refs) || !length(refs)) character() else refs[[1L]]
  }
  activity_sequence_advance <- function(outcome) {
    reihe <- activity_sequence()
    if (is.null(reihe)) return(invisible(NULL))
    ausgang <- c(reihe$outcomes, outcome)
    if (reihe$index >= length(reihe$keys)) {
      activity_sequence(NULL)
      activity_sequence_report(list(status="finished", total=length(reihe$keys), outcomes=ausgang))
      return(invisible(NULL))
    }
    weiter <- list(keys=reihe$keys, index=reihe$index + 1L, outcomes=ausgang)
    if (is.null(activity_sequence_resolve(weiter$keys[seq(weiter$index, length(weiter$keys))]))) {
      activity_sequence(NULL)
      activity_sequence_report(list(status="broken", total=length(reihe$keys), outcomes=ausgang))
      return(invisible(NULL))
    }
    activity_sequence_discard(TRUE)
    activity_sequence(weiter)
    invisible(NULL)
  }
  sync_activity_workflow <- function() {
    form <- activity_form()
    fields <- c('quantity_decimal','eligible_quantity_decimal','unit_price_decimal','gross_amount_decimal','monetary_fee_decimal','asset_fee_quantity_decimal','provided_basis_decimal')
    amounts_empty <- all(vapply(form[fields],function(value)is.character(value)&&length(value)==1L&&!nzchar(value),logical(1L)))
    if (is.null(activity_workflow)) {
      activity_workflow <<- new_data_asset_activity_workflow_v1(runtime_context_fingerprint(runtime$context),form)
    } else if (activity_workflow_reset_pending) {
      if (amounts_empty) {
        activity_workflow <<- new_data_asset_activity_workflow_v1(runtime_context_fingerprint(runtime$context),form)
        activity_workflow_reset_pending <<- FALSE
      }
    } else if (!is.null(activity_workflow_loading)) {
      expected <- activity_workflow_loading$form
      expected$local_date <- as.Date(expected$local_date)
      if (nzchar(expected$original_acquired_local_date)) expected$original_acquired_local_date <- as.Date(expected$original_acquired_local_date)
      for (name in c('quantity_decimal','eligible_quantity_decimal','unit_price_decimal','gross_amount_decimal','monetary_fee_decimal','asset_fee_quantity_decimal','provided_basis_decimal')) expected[[name]] <- desktop_product_manual_decimal_v1(expected[[name]])
      if (identical(form,expected)) {
        activity_workflow$accept_load(activity_workflow_loading$ticket,form)
        activity_workflow_loading <<- NULL
      }
    } else if (isTRUE(activity_workflow$view()$form_editable)) {
      current <- activity_workflow$view()
      # Ein Neuanlage-Formular ohne eingegebenen Betrag ist kein Entwurf. Seit das
      # Formular der Suche folgt (rc.226), aendert die App Portfolio, Asset und
      # Konto selbst - und jeder Assetwechsel in der Suche galt damit als
      # "ungespeicherte Eingabe": Die Uebergabe ins Formular wurde mit
      # "Transaktionsentwurf bleibt erhalten" verweigert, und eine Buchungszeile
      # liess sich erst nach ausdruecklichem Verwerfen waehlen, obwohl nichts
      # eingegeben war. Dieselbe Regel wendet refresh_activity_catalog() fuer
      # seine Sperre an: Geschuetzt werden eingegebene Werte, nicht der Kontext.
      if (identical(current$action,'create') && !length(current$selected_refs) && amounts_empty && !identical(activity_workflow$form(),form)) {
        activity_workflow <<- new_data_asset_activity_workflow_v1(runtime_context_fingerprint(runtime$context),form)
      } else activity_workflow$set_form(form)
    }
    activity_workflow_view(activity_workflow$view())
    activity_workflow$view()
  }
  require_activity_workflow <- function(action) {
    view <- sync_activity_workflow()
    if (activity_workflow_reset_pending) stop("activity_workflow_reset_pending",call.=FALSE)
    if (isTRUE(activity_workflow_completed())) stop("activity_workflow_already_completed",call.=FALSE)
    if (!identical(view$selected_refs,workflow_refs())) stop("activity_workflow_selection_pending",call.=FALSE)
    if (!identical(view$action,action) || !isTRUE(view$can_prepare) || !is.null(activity_workflow_loading))
      stop("activity_workflow_action_blocked",call.=FALSE)
    if (identical(action,"correct")) {
      original <- data_asset_activity_correction_prefill_v1(correction_center,activity_editor,runtime$context,view$selected_refs[[1L]])
      if (!identical(activity_form()$portfolio_ref,original$portfolio_ref)) stop("activity_workflow_correction_portfolio_changed",call.=FALSE)
    }
    view
  }
  # --- Steuerliche Einstellungen (#367) -----------------------------------
  # Denselben Dienst wie die Einzelasset-Maske: ein Steuerspeicher, ein
  # Einrichtungsweg. Ein zweiter waere ein zweiter Ort fuer dieselbe Wahrheit.
  tax_service <- asset_center_tax_service
  tax_model <- shiny::reactiveVal(NULL)
  tax_catalog <- shiny::reactiveVal(NULL)
  tax_notice <- shiny::reactiveVal(NULL)
  tax_plugin_from_note <- shiny::reactiveVal(NULL)
  # Ein dateInput liefert ein Date-Objekt, die Befehle erwarten ISO-Text.
  .data_tax_iso_date_v1 <- function(value) {
    if (inherits(value, "Date") && length(value) == 1L && !is.na(value)) format(value, "%Y-%m-%d") else ""
  }
  tax_labels <- shiny::reactiveVal(list())
  tax_now <- function() format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ")
  tax_failed <- function(error) {
    tax_notice(list(tone = "error", title = "Vorgang abgebrochen",
      copy = pl_error_text_v1(if (is.null(error$code)) conditionMessage(error) else error$code)))
    NULL
  }
  tax_safe <- function(expression) tryCatch(expression, error = tax_failed)
  tax_read <- function() {
    if (is.null(tax_service) || !isTRUE(tax_service$initialized())) return(invisible(NULL))
    payload <- tax_safe(tax_service$catalog())
    if (is.null(payload)) return(invisible(NULL))
    # Der Katalog liegt unter payload$catalog; Modul- und Definitionskataloge
    # stehen daneben.
    catalog <- list(portfolios = payload$catalog$portfolios, assets = payload$catalog$assets,
                    definition_catalog = payload$definition_catalog, plugin_catalog = payload$plugin_catalog)
    tax_catalog(catalog)
    labels <- list()
    for (asset in catalog$assets) labels[[asset$exchange_ref]] <- asset$display_name
    tax_labels(labels)
    shiny::updateSelectInput(session, "data_tax_portfolio",
      choices = stats::setNames(vapply(catalog$portfolios, `[[`, character(1L), "exchange_ref"),
                                vapply(catalog$portfolios, `[[`, character(1L), "display_name")))
    active <- Filter(function(a) identical(a$status, "active"), catalog$assets)
    # Deutsche Namen, die Kennung als Wert (#427): eine Klassifikation hat hier denselben Namen wie bei der Abweichung je Asset.
    shiny::updateSelectInput(session, "data_tax_type",
      choices = data_tax_named_choices_v1(data_tax_asset_type_labels_v1(), vapply(active, `[[`, character(1L), "asset_type")))
    codes <- vapply(catalog$definition_catalog$classifications, `[[`, character(1L), "classification_code")
    shiny::updateSelectInput(session, "data_tax_type_code", choices = data_tax_named_choices_v1(data_tax_classification_labels_v1(), codes))
    # Freistellungsauftrag, Quellensteuer und die Kapital-Verlusttoepfe gelten je Institut und stehen in deren Karte;
    # ein Wert ohne Institut wirkte in der Jahresrechnung nicht (Festlegung 14.10.2026).
    parameter_codes <- vapply(catalog$definition_catalog$parameters, `[[`, character(1L), "parameter_code")
    parameter_codes <- setdiff(parameter_codes, c(names(data_institution_tax_fields_v1()), "externally_used_capital_income_allowance"))
    shiny::updateSelectInput(session, "data_tax_parameter",
      choices = data_tax_named_choices_v1(data_tax_parameter_labels_v1(), parameter_codes))
    invisible(NULL)
  }
  tax_overview <- function() {
    portfolio <- input$data_tax_portfolio
    if (is.null(tax_service) || !isTRUE(tax_service$initialized()) || !is.character(portfolio) || !nzchar(portfolio)) return(invisible(NULL))
    value <- tax_safe(tax_service$overview(portfolio, as.integer(input$data_tax_year)))
    if (is.null(value)) return(invisible(NULL))
    tax_model(value)
    plugins <- value$plugin_catalog
    # Das Feld zeigt, was fuer die gewaehlte Projektionsart gilt - nicht, was
    # zuletzt angeklickt war. Sonst steht dort v1, waehrend v2 gespeichert ist
    # (#367).
    selected <- NULL
    for (s in value$selections) if (identical(s$projection_mode, input$data_tax_mode)) selected <- s$plugin_id
    # Ohne bisherige Wahl die empfohlene Fassung vorschlagen, nicht die erste der Liste (das Vergleichsmodell, #527).
    if (is.null(selected)) for (p in plugins) if (isTRUE(p$recommended)) selected <- p$plugin_id
    shiny::updateSelectInput(session, "data_tax_plugin",
      choices = stats::setNames(vapply(plugins, `[[`, character(1L), "plugin_id"),
                                vapply(plugins, function(p) paste0(data_tax_plugin_label_v1(p$plugin_id, p$plugin_version),
                                  if (isTRUE(p$recommended)) " · empfohlen" else ""), character(1L))),
      selected = selected)
    # Die Fassungskette verlangt ein streng spaeteres "Gueltig ab" als die vorige
    # Auswahl. Der 1. Januar ist fachlich richtig, aber bei jeder Wiederauswahl im
    # selben Jahr nicht mehr spaeter - der Schreibvorgang scheiterte dann mit
    # tax_ui_domain_write_failed, ohne das Feld zu nennen (#368, 28.09.2026).
    current_from <- NULL
    for (s in value$selections) if (identical(s$projection_mode, input$data_tax_mode)) current_from <- s$effective_from
    january <- as.Date(paste0(as.integer(input$data_tax_year), "-01-01"))
    earliest <- if (is.null(current_from)) january else max(january, as.Date(current_from) + 1L)
    shiny::updateDateInput(session, "data_tax_plugin_from", value = earliest, min = earliest)
    tax_plugin_from_note(if (is.null(current_from) || earliest <= january) NULL else
      paste0("Die bisherige Auswahl gilt ab ", format(as.Date(current_from), "%d.%m.%Y"),
             ". Eine neue Fassung braucht ein spaeteres Datum; vorgeschlagen ist der ",
             format(earliest, "%d.%m.%Y"), ". Das Datum ordnet nur die Fassungskette — welche Auswahl gilt, entscheidet die juengste Fassung."))
    invisible(NULL)
  }
  # Der Bewertungsstand bleibt unberuehrt: Diese Karten lesen und schreiben
  # ausschliesslich den Steuerspeicher.
  tax_apply <- function(command, payload, title) {
    if (is.null(tax_service)) {
      tax_notice(list(tone = "error", title = "Steuerbereich nicht verfügbar",
        copy = "Der lokale Steuerspeicher ist nicht lesbar.")); return(invisible(NULL))
    }
    preview <- tax_safe(tax_service$preview(command, payload))
    if (is.null(preview)) return(invisible(NULL))
    result <- tax_safe(tax_service$confirm_apply(preview$preview_ref, TRUE))
    if (is.null(result)) return(invisible(NULL))
    tax_notice(list(tone = "neutral", title = title, copy = "Übernommen; abhängige Projektionen sind als neu zu rechnen vermerkt."))
    tax_overview()
    # Ein Parameter der allgemeinen Karte kann eine Angabe der Jahreskarte sein - sie zeigt denselben Stand.
    tax_years_read(); tax_parameter_read()
  }
  # Die Karte "Weitere Steuerparameter je Jahr" hat ihr eigenes Jahr (#498) und zeigt alle Werte dieses Jahres mit Herkunft.
  tax_parameter_model <- shiny::reactiveVal(NULL)
  tax_parameter_year <- function() { year <- suppressWarnings(as.integer(input$data_tax_parameter_year)); if (length(year) != 1L || is.na(year)) as.integer(format(Sys.Date(), "%Y")) else year }
  tax_parameter_read <- function() {
    portfolio <- tax_portfolio()
    if (is.null(tax_service) || !isTRUE(tax_service$initialized()) || !nzchar(portfolio)) { tax_parameter_model(NULL); return(invisible(NULL)) }
    tax_parameter_model(tryCatch(tax_service$overview(portfolio, tax_parameter_year()), error = function(error) NULL))
    invisible(NULL)
  }
  shiny::observeEvent(list(input$data_tax_parameter_year, input$data_tax_portfolio), tax_parameter_read(), ignoreInit = TRUE)
  tax_portfolio <- function() .data_tax_text_v1(input$data_tax_portfolio, "")
  # Steuerangaben je Jahr: alle Jahre seit 2020 mit dem, was eingetragen ist und was fehlt.
  tax_years <- shiny::reactiveVal(list())
  tax_years_notice <- shiny::reactiveVal(NULL)
  tax_years_read <- function() {
    portfolio <- tax_portfolio()
    if (is.null(tax_service) || !isTRUE(tax_service$initialized()) || !nzchar(portfolio)) { tax_years(list()); return(invisible(NULL)) }
    years <- seq.int(2020L, max(2020L, as.integer(format(Sys.Date(), "%Y"))))
    tax_years(lapply(years, function(year) data_tax_year_row_v1(year, tryCatch(tax_service$overview(portfolio, year), error = function(error) NULL))))
    invisible(NULL)
  }
  output$data_tax_years_form <- shiny::renderUI(data_tax_years_form_v1(tax_years()))
  output$data_tax_years_notice <- shiny::renderUI({
    current <- tax_years_notice()
    if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone)
  })
  shiny::observeEvent(input$data_tax_years_save, {
    if (!tax_ready()) return()
    rows <- tax_years()
    if (!length(rows)) { tax_years_notice(list(tone = "warning", title = "Noch nichts gelesen", copy = "Zuerst oben „Einstellungen lesen“ drücken.")); return() }
    plan <- data_tax_year_commands_v1(rows, function(year) list(rate = input[[paste0("data_tax_years_rate_", year)]],
      church = input[[paste0("data_tax_years_church_", year)]], church_rate = input[[paste0("data_tax_years_church_rate_", year)]]), tax_portfolio())
    if (!is.null(plan$error)) { tax_years_notice(list(tone = "error", title = "Nicht gespeichert", copy = plan$error)); return() }
    # Veranlagungsart je Jahr (#498): ohne Rechnungsfolge, deshalb ohne Vermerk "neu zu rechnen".
    assessments <- data_tax_year_assessment_changes_v1(rows, function(year) input[[paste0("data_tax_years_assessment_", year)]])
    assessment_failed <- NULL
    for (item in assessments) {
      done <- tryCatch({ tax_service$assessment_record(item$year, item$assessment); TRUE }, error = function(error) if (is.null(error$code)) conditionMessage(error) else error$code)
      if (!isTRUE(done)) { assessment_failed <- sprintf("%d, Veranlagung: %s", item$year, pl_error_text_v1(done)); break }
    }
    # Zaehlt das Portfolio im Jahr zur Veranlagung (#501)? Wirkt auf Jahresrechnung und Netto-Sicht beim naechsten Rechnen.
    scopes <- if (is.null(assessment_failed)) data_tax_year_scope_changes_v1(rows, function(year) input[[paste0("data_tax_years_counts_", year)]]) else list()
    for (item in scopes) {
      done <- tryCatch({ tax_service$scope_record(item$year, item$counts); TRUE }, error = function(error) if (is.null(error$code)) conditionMessage(error) else error$code)
      if (!isTRUE(done)) { assessment_failed <- sprintf("%d, zählt zur Veranlagung: %s", item$year, pl_error_text_v1(done)); break }
    }
    if (!length(plan$commands)) {
      tax_years_read(); tax_parameter_read()
      tax_years_notice(if (!is.null(assessment_failed)) list(tone = "error", title = "Nicht gespeichert", copy = assessment_failed)
        else if (length(scopes)) list(tone = "positive", title = sprintf("„zählt zur Veranlagung“ für %d Jahr(e) gespeichert", length(scopes)),
          copy = "Jahresrechnung und Netto-Sicht rechnen damit nach dem nächsten „Alles aktualisieren“.")
        else if (length(assessments)) list(tone = "positive", title = sprintf("Veranlagung für %d Jahr(e) gespeichert", length(assessments)),
          copy = "Sie bestimmt den Sparer-Pauschbetrag in der Übersicht der Werte je Jahr.")
        else list(tone = "neutral", title = "Nichts geändert", copy = "Die Angaben stimmen mit dem gespeicherten Stand überein."))
      return()
    }
    written <- 0L; failed <- NULL
    for (item in plan$commands) {
      done <- tryCatch({ preview <- tax_service$preview(item$command, item$payload); tax_service$confirm_apply(preview$preview_ref, TRUE); TRUE },
        error = function(error) if (is.null(error$code)) conditionMessage(error) else error$code)
      if (!isTRUE(done)) { failed <- sprintf("%d, %s: %s", item$year, data_tax_year_parameter_label_v1(item$code), pl_error_text_v1(done)); break }
      written <- written + 1L
    }
    tax_overview(); tax_years_read(); tax_parameter_read()
    years <- sort(unique(vapply(plan$commands[seq_len(written)], function(item) as.integer(item$year), integer(1L))))
    tax_years_notice(if (is.null(failed)) list(tone = "positive", title = sprintf("%d Angabe(n) gespeichert", written),
        copy = sprintf("Steuerjahr(e) %s. Die Projektionen sind als neu zu rechnen vermerkt – bitte „Alles aktualisieren“ (oben rechts) starten.",
          paste(years, collapse = ", ")))
      else list(tone = "error", title = sprintf("Abgebrochen nach %d gespeicherten Angabe(n)", written), copy = paste("Nicht gespeichert:", failed)))
  })
  # Ohne gewaehltes Portfolio brach jeder Knopf stumm ab. Wer nichts sieht,
  # sucht den Fehler bei sich (Festlegung 28.09.2026, #367).
  tax_ready <- function() {
    if (nzchar(tax_portfolio())) return(TRUE)
    tax_notice(list(tone = "warning", title = "Kein Portfolio gewählt",
      copy = "Zuerst \u201eEinstellungen lesen\u201c drücken und dann ein Portfolio wählen; erst dann lässt sich etwas setzen."))
    FALSE
  }
  output$data_tax_plugin_from_note <- shiny::renderUI({
    copy <- tax_plugin_from_note()
    if (is.null(copy)) NULL else portelyra_status_panel("Gültig ab angepasst", copy, tone = "neutral")
  })
  institution_tax <- data_institution_tax_server_v1(input, output, session, institution_tax_service, project_root, now_utc, kinds_service = institution_master_service)
  institution_master_area <- data_institution_master_server_v1(input, output, session, institution_master_service, now_utc,
    on_saved = function() if (!is.null(shiny::isolate(input$data_institution_tax_year))) institution_tax$read())
  advance_lump_sum <- data_advance_lump_sum_server_v1(input, output, session, advance_lump_sum_service, now_utc)
  tax_document <- data_tax_document_server_v1(input, output, session, tax_document_service, now_utc)
  # Leser (rc.380, #486): gelesen erst, wenn der Unterreiter offen ist; der Selbsttest laeuft im Hintergrund.
  price_providers_service <- tryCatch(new_data_price_providers_service_v1(project_root, runtime$context), error = function(error) NULL)
  price_providers <- data_price_providers_server_v1(input, output, session, price_providers_service,
    active = shiny::reactive(identical(input$asset_center_step, "transactions") && identical(input$transactions_view, "price_providers")))
  # Zugaenge (#546, rc.389): gelesen erst, wenn die Einstellungen offen sind.
  plugin_credentials <- data_plugin_credentials_server_v1(input, output, session, tryCatch(new_data_plugin_credentials_service_v1(project_root, runtime$context), error = function(error) NULL),
    active = shiny::reactive(isTRUE(input$settings_panel_open)))
  statement_readers <- data_statement_readers_server_v1(input, output, session, tryCatch(new_data_statement_readers_service_v1(project_root, runtime$context), error = function(error) NULL),
    active = shiny::reactive(identical(input$asset_center_step, "transactions") && identical(input$transactions_view, "readers")), now_utc = now_utc)
  portfolio_history_service <- tryCatch(new_data_portfolio_snapshot_service_v1(project_root, runtime$context), error = function(error) NULL)
  portfolio_history <- data_portfolio_history_server_v1(input, output, session, portfolio_history_service, now_utc)
  # Nach gespeicherter Zugehoerigkeit rechnet die Analyse erst mit einer neuen Veroeffentlichung der Tageshistorie (#481).
  investment_scope_area <- data_investment_scope_server_v1(input, output, session, investment_scope_service, now_utc,
    publish = function() if (is.null(portfolio_history_service)) NULL else portfolio_history_service$history_publish(now_utc()))
  # Vergleichsindex und eigene Gruppen (#482, #483): nach dem Speichern rechnet die Analyse mit einer neuen Veroeffentlichung.
  analysis_settings_area <- data_analysis_settings_server_v1(input, output, session, analysis_settings_service, now_utc,
    publish = function() if (is.null(portfolio_history_service)) NULL else portfolio_history_service$history_publish(now_utc()))
  # Reiter "Einstellungen" (#500): Anzeige fuer alle Apps, Aufbewahrung der Tageshistorie.
  user_settings_area <- data_user_settings_server_v1(input, output, session, user_settings_service, now_utc,
    space = tryCatch(runtime_data_space_path(runtime$context), error = function(error) NULL))
  # Speicher aufraeumen (#438): Zwischenstaende des Buchungsbestands und ueberholte Bewertungslaeufe, mit Vorschau und Bestaetigung.
  storage_retention_area <- data_storage_retention_server_v1(input, output, session, storage_retention_service, now_utc)
  output$data_expert_tools <- shiny::renderText(if (isTRUE(user_settings_area$expert())) "on" else "off")
  shiny::outputOptions(output, "data_expert_tools", suspendWhenHidden = FALSE)
  # Umfang je Portfolio (#542): gelesen nach dem ersten Lesen der Stammdaten und wieder, wenn ein Portfolio hinzukommt oder archiviert
  # wird (beim ersten Lesen legt der Kern den Bestandseintrag an). Daraus die Ausgaben data_module_<key> fuer die Bereiche und was das
  # gewaehlte Portfolio in Formularen und Importen anbietet; dazu die gefuehrte Einrichtung.
  portfolio_configuration_service <- tryCatch(new_data_portfolio_configuration_service_v1(project_root, runtime$context), error = function(error) NULL)
  # Passwortschutz (#535): einrichten, Klartext entfernen, Passwort aendern; nach dem Einrichten beendet sich Portelyra.
  data_protection_server_v1(input, output, session, project_root, runtime$home, stopper = data_protection_stopper_v1())
  # Backups ohne Kommandozeile (#559, rc.407): gesperrt, solange ein Lauf, Zeitlauf oder Sammellauf die Sperre haelt - mit Namen.
  data_backups_server_v1(input, output, session, data_backups_deps_v1(project_root, runtime$home,
    busy = function() if (refresh_all_background_busy()) refresh_all_holder_copy("Ihn abwarten, dann erneut versuchen.") else NULL))
  # „Umfang: …“ im Block links (#542): der wirksame Umfang, wie ihn der Kern liest - in den Anzeige-Apps aus den veroeffentlichten
  # Einstellungen. Das Server-Modul unten liefert den Stand.
  desktop_activity_scope_server_v1(output, shiny::reactive({
    value <- if (is.list(portfolio_configuration)) portfolio_configuration$state() else NULL
    if (!is.list(value) || !is.null(attr(value, "code")) || !is.character(value$effective_scope_text)) return(NULL)
    list(effective_scope_text = value$effective_scope_text, modules = value$effective$modules, source = "published")
  }))
  portfolio_configuration <- data_portfolio_configuration_server_v1(input, output, session, portfolio_configuration_service,
    portfolio = shiny::reactive({ asset_center_catalog(); data_portfolio_configuration_portfolio_v1(asset_center_catalog_editor, input$asset_center_portfolio) }),
    portfolios_key = shiny::reactive({ asset_center_catalog(); data_portfolio_configuration_key_v1(asset_center_catalog_editor) }),
    settings_open = shiny::reactive(isTRUE(input$settings_panel_open)),
    # Marktdaten ab- oder zuschalten stellt die bestehenden Assets mit um (Festlegung 10.11.2026) - je Asset derselbe Weg wie die Karte
    # "Bewertung ueber die Zeit": Katalogbefehl "revise_valuation_method", dann die Zeitleiste. Der Dienst entsteht weiter unten.
    switcher = list(
      timeline = list(preview = function(asset_id, segments) asset_valuation_timeline_service$preview(asset_id, segments),
                      apply = function(preview, confirmed) asset_valuation_timeline_service$apply(preview, confirmed)),
      catalog_revise = function(method, asset_id) {
        desktop_catalog_editor_refresh_v1(asset_center_catalog_editor, runtime$context)
        ref <- names(Filter(function(row) identical(row$asset_id, asset_id), asset_center_catalog_editor$catalog$maps$asset))
        if (length(ref) != 1L) stop(structure(class = c("spot_desktop_catalog_error_v1", "error", "condition"),
          list(message = "desktop_catalog_input_invalid", call = NULL, code = "desktop_catalog_input_invalid")))
        form <- list(action = "revise_valuation_method", entity_type = "asset", entity_ref = ref, portfolio_ref = "", display_name = "",
          base_currency = "EUR", account_type = "securities", institution_label = "", asset_type = "other", price_currency = "EUR",
          quantity_scale = "0", valuation_method = method, isin = "")
        prepared <- desktop_catalog_editor_prepare_v1(asset_center_catalog_editor, runtime$context, form, now_utc())
        desktop_catalog_editor_execute_v1(asset_center_catalog_editor, runtime$context, prepared, TRUE)
      },
      assets_changed = function() {
        tryCatch(asset_center_refresh(shiny::isolate(input$asset_center_asset)), error = function(error) NULL)
        tryCatch(asset_center_valuation_workflow$invalidate(), error = function(error) NULL)
      }))
  # Gesendet wird nur, was sich gegenueber dem zuletzt Gesendeten aendert. Vorgabe ist der volle Stand: Mit allen Klassen und Bausteinen
  # (und ohne gelesenen Umfang) geht keine Nachricht an den Browser, alles bleibt wie bisher.
  scope_sent <- new.env(parent = emptyenv())
  assign("import_kind", desktop_import_kind_choices_v1(), envir = scope_sent)
  assign("asset_center_type", data_asset_center_type_choices_v1(), envir = scope_sent)
  assign("asset_center_domain", data_asset_center_domain_choices_v1(), envir = scope_sent)
  assign("asset_center_valuation", list(choices = data_asset_center_valuation_choices_v1(), selected = "external_market"), envir = scope_sent)
  scope_send <- function(id, value, send) {
    if (identical(scope_sent[[id]], value)) return(invisible(FALSE))
    assign(id, value, envir = scope_sent); send(); invisible(TRUE)
  }
  # Eine Art, die der Eingang oder eine Vorbelegung (Import, Suche beim Kursanbieter) mitbringt, bleibt waehlbar - auch wenn das
  # Portfolio sie nicht waehlt; der Hinweis am Formular sagt es.
  import_kind_keep <- shiny::reactiveVal(NULL)
  asset_center_type_keep <- shiny::reactiveVal(NULL)
  shiny::observeEvent(input$asset_center_portfolio, { import_kind_keep(NULL); asset_center_type_keep(NULL) }, ignoreInit = TRUE)
  shiny::observe({
    types <- portfolio_configuration$asset_types(); keep <- import_kind_keep(); all <- desktop_import_kind_choices_v1()
    choices <- desktop_import_kind_choices_v1(types)
    if (!is.null(keep) && keep %in% unname(all)) choices <- all[unname(all) %in% c(unname(choices), keep)]
    scope_send("import_kind", choices, function() {
      current <- shiny::isolate(input$import_kind)
      shiny::updateRadioButtons(session, "import_kind", choices = choices, inline = TRUE,
        selected = if (!is.null(keep) && keep %in% choices) keep else if (isTRUE(current %in% choices)) current else unname(choices)[[1L]])
    })
  })
  output$import_kind_scope_note <- shiny::renderUI({
    types <- portfolio_configuration$asset_types(); if (is.null(types)) return(NULL)
    if (length(desktop_import_kind_choices_v1(types)) == length(desktop_import_kind_choices_v1())) return(NULL)
    shiny::p(class = "pl-field-hint", "Angeboten werden die Importe der Klassen dieses Portfolios; weitere unter Einstellungen → Portfolio → Umfang.")
  })
  shiny::observe({
    types <- portfolio_configuration$asset_types(); keep <- asset_center_type_keep()
    choices <- data_portfolio_configuration_asset_type_choices_v1(data_asset_center_type_choices_v1(), types, keep)
    scope_send("asset_center_type", choices, function() {
      current <- shiny::isolate(input$asset_center_type)
      shiny::updateSelectInput(session, "asset_center_type", choices = choices,
        selected = if (!is.null(keep) && keep %in% choices) keep else if (isTRUE(current %in% choices)) current else unname(choices)[[1L]])
    })
    domains <- data_portfolio_configuration_domain_choices_v1(data_asset_center_domain_choices_v1(), types)
    scope_send("asset_center_domain", domains, function() {
      current <- shiny::isolate(input$asset_center_domain)
      # Die Art bleibt eine ausdrueckliche Wahl (#364): Ohne passende Wahl ist keine vorbelegt.
      shiny::updateRadioButtons(session, "asset_center_domain", choices = domains, selected = if (isTRUE(current %in% domains)) current else character(0))
    })
    # Ohne Marktdaten (Festlegung 10.11.2026): Die Bewertung ohne Kursabruf ist vorbelegt; bestehende Assets behalten ihre Art.
    valuation <- data_portfolio_configuration_valuation_choices_v1(data_asset_center_valuation_choices_v1(), portfolio_configuration$configuration()) %||%
      list(choices = data_asset_center_valuation_choices_v1(), selected = "external_market")
    scope_send("asset_center_valuation", valuation, function()
      shiny::updateSelectInput(session, "asset_center_valuation", choices = valuation$choices, selected = valuation$selected))
  })
  # Ein Vorschlag des Kursanbieters bringt seine Art mit (vor dem Uebernehmen im Formular; dort setzt der Beobachter die Auswahl).
  shiny::observeEvent(input$asset_center_provider_candidate_apply, {
    if (!identical(input$asset_center_mode, "new") || is.null(portfolio_configuration$asset_types())) return()
    candidate <- tryCatch(asset_center_provider_search_service$resolve_candidate(input$asset_center_provider_candidate), error = function(error) NULL)
    type <- if (is.null(candidate)) NULL else tryCatch(data_asset_center_candidate_master_v1(candidate, input$asset_center_isin)$asset_type, error = function(error) NULL)
    if (!is.null(type)) asset_center_type_keep(type)
  }, priority = 10)
  output$asset_center_new_scope_note <- shiny::renderUI({
    types <- portfolio_configuration$asset_types()
    filtered <- !is.null(types) && length(data_portfolio_configuration_asset_type_choices_v1(data_asset_center_type_choices_v1(), types)) <
      length(data_asset_center_type_choices_v1())
    data_portfolio_configuration_new_asset_note_ui_v1(portfolio_configuration$entry(), filtered)
  })
  # Ein bestehendes Asset einer Klasse, die das Portfolio nicht waehlt: bleibt bearbeitbar, mit Hinweis (nichts verschwindet still).
  output$asset_center_scope_note <- shiny::renderUI({
    types <- portfolio_configuration$asset_types(); if (is.null(types)) return(NULL)
    asset <- asset_center_selected(); if (is.null(asset) || isTRUE(asset$asset_type %in% types)) return(NULL)
    data_portfolio_configuration_asset_note_ui_v1(asset$asset_type, types, portfolio_configuration$catalog())
  })
  # Wertermittlung je Wallet (rc.294): Die Wahl aendert den FIFO-Stand - erst fortschreiben, dann die Tageshistorie neu veroeffentlichen.
  crypto_method_area <- data_crypto_method_server_v1(input, output, session, crypto_method_service, now_utc, after_write = function() {
    materialized <- update_realized_state("incremental", tolerate_failure = TRUE)
    if (is.null(materialized) || is.null(portfolio_history_service)) return(NULL)
    published <- tryCatch(portfolio_history_service$history_publish(now_utc()), error = function(error) NULL)
    if (is.list(published) && published$status %in% c("published", "already_published")) "published" else NULL
  })
  # Dieselben Schritte nach dem Speichern wie bei der Wertermittlung (#508).
  fifo_wallet_area <- data_fifo_wallet_server_v1(input, output, session, fifo_wallet_service, now_utc, after_write = function() {
    materialized <- update_realized_state("incremental", tolerate_failure = TRUE)
    if (is.null(materialized) || is.null(portfolio_history_service)) return(NULL)
    published <- tryCatch(portfolio_history_service$history_publish(now_utc()), error = function(error) NULL)
    if (is.list(published) && published$status %in% c("published", "already_published")) "published" else NULL
  })
  # Aktiensplit (#451): dieselben Schritte nach dem Speichern - FIFO-Stand fortschreiben, Tageshistorie neu veroeffentlichen.
  stock_split_area <- data_stock_split_server_v1(input, output, session, stock_split_service, now_utc, after_write = function() {
    materialized <- update_realized_state("incremental", tolerate_failure = TRUE)
    if (is.null(materialized) || is.null(portfolio_history_service)) return(NULL)
    published <- tryCatch(portfolio_history_service$history_publish(now_utc()), error = function(error) NULL)
    if (is.list(published) && published$status %in% c("published", "already_published")) "published" else NULL
  })
  shiny::observeEvent(input$data_tax_refresh, { tax_read(); tax_overview(); tax_years_read(); tax_parameter_read(); institution_tax$read(); advance_lump_sum$read(); tax_document$read() })
  shiny::observeEvent(list(input$data_tax_portfolio, input$data_tax_year, input$data_tax_mode),
                      tax_overview(), ignoreInit = TRUE)
  shiny::observeEvent(input$data_tax_portfolio, { tax_years_notice(NULL); tax_years_read() }, ignoreInit = TRUE)
  # Der Reiter liest beim ersten Oeffnen selbst; das Portfolio kommt mit dem Katalog und loest Ueberblick und Jahre aus.
  shiny::observeEvent(input$asset_center_step, {
    if (identical(input$asset_center_step, "3 · Steuer") && is.null(tax_catalog())) { tax_read(); institution_tax$read(); advance_lump_sum$read() }
    # Die Liste der Ertraegnisaufstellungen folgt der Ablage (#536): nach „Art ändern“ steht die Aufstellung beim naechsten Oeffnen da.
    if (identical(input$asset_center_step, "3 · Steuer")) tax_document$read()
  })
  # Neue Fassung uebernehmen (#486 Schritt 2): genau die angebotene Fassung (Schluessel aus der Uebersicht), fuer alle Projektionsarten
  # zugleich (Festlegung 16.11.2026) mit einem gemeinsamen "Gueltig ab" - streng nach der juengsten bisherigen Auswahl, wie die
  # Fassungskette es je Projektionsart verlangt.
  output$data_tax_module_updates <- shiny::renderUI(data_tax_module_updates_ui_v1(tax_model()))
  for (update_index in 1:3) local({
    index <- update_index
    shiny::observeEvent(input[[paste0("data_tax_module_adopt_", index)]], {
      if (!tax_ready()) return()
      updates <- tax_model()$module_updates
      if (!is.list(updates) || index > length(updates)) return()
      update <- updates[[index]]
      modes <- as.character(unlist(update$projection_modes, use.names = FALSE))
      froms <- as.Date(unlist(lapply(tax_model()$selections, function(s) if (isTRUE(s$projection_mode %in% modes)) s$effective_from else NULL), use.names = FALSE))
      chosen <- as.Date(input$data_tax_module_adopt_from)
      if (length(chosen) != 1L || is.na(chosen)) chosen <- Sys.Date()
      if (length(froms) && chosen <= max(froms)) chosen <- max(froms) + 1L
      for (mode in modes) tax_apply("select_plugin", list(portfolio_ref = tax_portfolio(), projection_mode = mode, plugin_id = update$plugin_id,
        effective_from = format(chosen, "%Y-%m-%d"), status = "active", module_key = update$module_key),
        sprintf("Neue Fassung übernommen (%s)", if (mode %in% names(DATA_TAX_MODE_LABELS_V1)) DATA_TAX_MODE_LABELS_V1[[mode]] else mode))
    }, ignoreInit = TRUE)
  })
  # Neue Fassung aus Datei (#486 Schritt 2c): pruefen (schreibt nichts), dann bestaetigt installieren - genau die gezeigte Vorschau.
  tax_module_install_preview <- shiny::reactiveVal(NULL)
  output$data_tax_module_install_preview <- shiny::renderUI(data_tax_module_install_preview_ui_v1(tax_module_install_preview()))
  # Seit #486 Schritt 3 startet die Pruefung das gemeinsame "Paket installieren" (Einstellungen -> "Plugins"); installiert wird genau die
  # dort gewaehlte Datei.
  tax_module_zip_path <- shiny::reactiveVal(NULL)
  shiny::observeEvent(input$data_plugin_package_file, { tax_module_install_preview(NULL); tax_module_zip_path(NULL) }, ignoreInit = TRUE)
  tax_module_check <- function(path) {
    if (is.null(tax_service)) { tax_notice(list(tone = "warning", title = "Steuereinstellungen nicht verfügbar", copy = "Der Steuerspeicher ist nicht lesbar.")); return() }
    tax_module_zip_path(path)
    tax_module_install_preview(tax_safe(tax_service$module_install_preview(path)))
  }
  shiny::observeEvent(input$data_tax_module_install, {
    preview <- tax_module_install_preview(); path <- tax_module_zip_path()
    if (!is.list(preview) || !isTRUE(preview$installable) || is.null(path)) return()
    if (!isTRUE(input$data_tax_module_install_seen)) {
      tax_notice(list(tone = "warning", title = "Bitte bestätigen", copy = "Erst das Häkchen „Ich habe Fassung und Unterschiede gesehen“ setzen.")); return()
    }
    result <- tax_safe(tax_service$module_install_apply(path, preview$preview_fingerprint))
    if (is.null(result)) return()
    tax_module_install_preview(NULL)
    tax_notice(list(tone = "positive", title = paste0("Fassung ", result$plugin_version, " installiert"),
      copy = "Sie steht jetzt oben unter „Neue Fassung verfügbar“ und gilt, sobald Sie sie übernehmen."))
    tax_overview()
  })
  # Gemeinsamer Plugin-Verwalter (#486 Schritt 3): Liste und "Paket installieren" unter Einstellungen -> "Plugins"; gelesen erst, wenn die
  # Einstellungen offen sind. Leser-Pakete prueft der Leser-Server, Steuermodul-Pakete die Steuereinstellungen.
  plugin_manager <- data_plugin_manager_server_v1(input, output, session, tryCatch(new_data_plugin_manager_service_v1(project_root, runtime$context), error = function(error) NULL),
    active = shiny::reactive(isTRUE(input$settings_panel_open)), on_reader = statement_readers$check_install, on_tax = tax_module_check,
    on_provider = price_providers$check_install)
  shiny::observeEvent(input$data_tax_plugin_apply, {
    if (!tax_ready()) return()
    tax_apply("select_plugin", list(portfolio_ref = tax_portfolio(), projection_mode = input$data_tax_mode,
      plugin_id = input$data_tax_plugin, effective_from = .data_tax_iso_date_v1(input$data_tax_plugin_from), status = "active"),
      "Regelmodul übernommen")
  })
  tax_bucket_for <- function(code) {
    definitions <- tax_catalog()$definition_catalog$classifications
    hit <- Filter(function(d) identical(d$classification_code, code), definitions)
    if (!length(hit)) NULL else hit[[1L]]$tax_bucket
  }
  shiny::observeEvent(input$data_tax_type_apply, {
    bucket <- tax_bucket_for(input$data_tax_type_code)
    if (!tax_ready()) return()
    if (is.null(bucket)) {
      tax_notice(list(tone = "warning", title = "Keine Klassifikation gewählt",
        copy = "Die Klassifikation bestimmt den Steuertopf; ohne sie wird nichts gesetzt.")); return()
    }
    tax_apply("set_asset_type_classification", list(portfolio_ref = tax_portfolio(),
      asset_type = input$data_tax_type, classification_code = input$data_tax_type_code, tax_bucket = bucket,
      partial_exemption_rate_decimal = input$data_tax_type_partial,
      effective_from_year = as.integer(input$data_tax_type_from), effective_to_year = NULL),
      "Vorgabe je Asset-Typ gesetzt")
  })
  shiny::observeEvent(input$data_tax_type_retire, {
    if (!tax_ready()) return()
    tax_apply("retire_asset_type_classification", list(portfolio_ref = tax_portfolio(),
      asset_type = input$data_tax_type, effective_from_year = as.integer(input$data_tax_type_from)),
      "Vorgabe zurückgezogen")
  })
  shiny::observeEvent(input$data_tax_parameter_apply, {
    if (!tax_ready()) return()
    currency <- .data_tax_text_v1(input$data_tax_parameter_currency, "")
    tax_apply("set_parameter", list(portfolio_ref = tax_portfolio(), tax_year = tax_parameter_year(),
      parameter_code = input$data_tax_parameter, currency = if (nzchar(currency)) currency else NULL,
      value_decimal = input$data_tax_parameter_value), "Parameter gesetzt")
  })
  # Zuruecksetzen auf die Vorgabe des Regelmoduls (#529): Der Kern zieht die eigene Angabe als neue Fassung zurueck.
  shiny::observeEvent(input$data_tax_parameter_retire, {
    if (!tax_ready()) return()
    code <- .data_tax_text_v1(input$data_tax_parameter, "")
    if (!nzchar(code)) { tax_notice(list(tone = "warning", title = "Kein Parameter gewählt", copy = "Erst Jahr und Parameter wählen.")); return() }
    currency <- .data_tax_text_v1(input$data_tax_parameter_currency, "")
    tax_apply("retire_parameter", list(portfolio_ref = tax_portfolio(), tax_year = tax_parameter_year(), parameter_code = code,
      currency = if (nzchar(currency)) currency else NULL), "Eigene Angabe zurückgesetzt – es gilt die Vorgabe des Regelmoduls")
  })
  output$data_tax_state <- shiny::renderUI(data_tax_state_ui_v1(tax_model(), tax_notice()))
  output$data_tax_readiness <- shiny::renderTable(data_tax_readiness_frame_v1(tax_model()), striped = TRUE, spacing = "xs", width = "100%")
  output$data_tax_type_table <- shiny::renderTable(data_tax_type_frame_v1(tax_model()), striped = TRUE, spacing = "xs", width = "100%")
  output$data_tax_asset_table <- shiny::renderTable(data_tax_asset_frame_v1(tax_model(), tax_labels()), striped = TRUE, spacing = "xs", width = "100%")
  output$data_tax_inherited_table <- shiny::renderTable(data_tax_inherited_frame_v1(tax_model(), tax_labels()), striped = TRUE, spacing = "xs", width = "100%")
  output$data_tax_parameter_table <- shiny::renderTable(data_tax_parameter_values_frame_v1(tax_parameter_model()), striped = TRUE, spacing = "xs", width = "100%")
  output$data_tax_year_coverage <- shiny::renderUI(data_tax_year_coverage_ui_v1(tax_parameter_model()))
  output$data_tax_plugins <- shiny::renderTable({
    model <- tax_model(); if (is.null(model) || !length(model$plugin_catalog)) return(data.frame())
    rows <- model$plugin_catalog
    data.frame(
      Modul = vapply(rows, function(p) data_tax_plugin_label_v1(p$plugin_id), character(1L)),
      Fassung = vapply(rows, function(p) .data_tax_text_v1(p$plugin_version), character(1L)),
      Rechtsraum = vapply(rows, function(p) if (identical(p$jurisdiction_code, "DE")) "Deutschland" else .data_tax_text_v1(p$jurisdiction_code), character(1L)),
      Empfohlen = vapply(rows, function(p) if (isTRUE(p$recommended)) "ja" else "", character(1L)),
      stringsAsFactors = FALSE, check.names = FALSE)
  }, striped = TRUE, spacing = "xs", width = "100%")

  refresh_activity_corrections <- function() {
    selected <- workflow_refs()
    # Der Filter haengt nicht mehr am Asset-Feld des Buchungsformulars. Er hat
    # zweimal eine Buchung unsichtbar gemacht, die der Kern laengst lieferte.
    # Nichts sagte, dass dieses Feld die Liste steuert, und die Buchung wirkte
    # nicht korrigierbar. Wer nach einem Asset
    # sucht, tippt es in die Auswahl - die Suche liegt jetzt serverseitig, damit
    # das auch bei tausend Buchungen schnell bleibt.
    focus <- if (isTRUE(input$activity_correction_focus_asset))
      tryCatch(shiny::isolate(input$activity_asset), error=function(error) NULL) else NULL
    if (!is.character(focus) || length(focus) != 1L || is.na(focus) || !nzchar(focus)) focus <- NULL
    model<-data_asset_activity_correction_refresh_v1(
      correction_center, runtime$context, activity_editor, focus, selected
    );correction_model(model)
    # Ein neuer Beleg darf nicht hinter einer zuvor geleerten Anzeige verschwinden.
    # Nur setzen, nie lesen: Diese Funktion laeuft auch ausserhalb eines
    # reaktiven Kontexts, in dem das Lesen einer reactiveVal fehlschlaegt.
    if(length(model$history$rows)) correction_history_hidden(FALSE)
    # Das Dropdown ist durch die Tabelle ersetzt (#424); gewaehlt wird dort. Eine
    # Auswahl, die es nach dem Neulesen nicht mehr gibt, faellt von selbst weg,
    # weil die Tabelle nur vorhandene Zeilen zeichnet.
    model
  }
  update_realized_state <- function(mode="incremental", tolerate_failure=TRUE) {
    invoke<-function(callback)if(isTRUE(tolerate_failure))tryCatch(callback(),error=function(error)NULL)else callback()
    result<-invoke(function()realized_adapter$materialize(runtime$context,mode,now_utc(),"incomplete_quarantined_or_derivative_blocked"))
    model<-invoke(function()realized_adapter$read(runtime$context))
    realized_model(model);readiness_model(invoke(function()realized_adapter$readiness(runtime$context)))
    if(!is.null(result)) activity_read_view(invoke(function()data_asset_activity_editor_read_view_v1(activity_editor,runtime$context)))
    result
  }
  # Rechenstand in Worten (#422, rc.331); ein unbekanntes Kuerzel bleibt sichtbar.
  realized_freshness_label <- function(value) {
    text <- if (is.character(value) && length(value) == 1L && !is.na(value)) value else ""
    switch(text, fresh = "aktuell", stale = "liegt zurück", stale_pending = "Rechnung steht aus", stale_failed = "letzte Rechnung fehlgeschlagen",
      unavailable = "noch nichts gerechnet", if (nzchar(text)) text else "unbekannt")
  }
  activity_event_label <- function(value) {
    labels <- desktop_activity_type_choices_v1()
    hit <- names(labels)[unname(labels) == value]
    if (length(hit) == 1L) hit else value
  }
  refresh_realized_state <- function() {model<-realized_adapter$read(runtime$context);realized_model(model);readiness_model(realized_adapter$readiness(runtime$context));model}
  # Cash statement import (#184): load Cash catalog, preview, chunked booking, movement list.
  cash_statement_service <- new_data_cash_statement_import_v1(project_root, runtime$context)
  cash_import_preview <- shiny::reactiveVal(NULL)
  cash_import_result <- shiny::reactiveVal(NULL)
  cash_import_message <- shiny::reactiveVal(NULL)
  # Vom Eigentuemer bestaetigter Saldo am Stichtag (fuer Exporte ohne Saldoangabe).
  cash_import_confirmed <- shiny::reactiveVal(NULL)
  # Netto gebuchte Zinsertraege dieses Auszugs: eigene Vorschau neben dem Import (#465).
  cash_import_gross <- shiny::reactiveVal(NULL)
  cash_import_cleared_upload <- shiny::reactiveVal(NULL)
  cash_movements_model <- shiny::reactiveVal(NULL)
  # Wertpapier-Belege (#446): pruefen, Konto je Depot, neue Vorgaenge ueber den Aktivitaeten-CSV-Import buchen.
  # Rueckmeldung in der Karte selbst (UX-Fluss: dort, wo geprueft und geklickt wird).
  securities_statement_service <- new_data_securities_statement_import_v1(project_root, runtime$context)
  # Pruefstand je Portfolio (rc.380) fuer Ablaeufe ohne eigenen Vorschau-Befehl (Rewards).
  statement_reader_check_service <- new_data_statement_reader_check_service_v1(project_root, runtime$context)
  # Experimenteller generischer Leser (#514): Zuordnung vorschlagen und als Profil speichern; die Dateien sind die der Importkarte.
  generic_statement_area <- data_generic_statement_server_v1(input, output, session, new_data_generic_statement_service_v1(project_root, runtime$context),
    files = function() securities_import_selection())
  securities_import_result <- shiny::reactiveVal(NULL)
  securities_import_message <- shiny::reactiveVal(NULL)
  securities_import_safe <- function(expression, success) tryCatch(
    .desktop_product_force_before_success_v1(expression, success),
    error = function(error) {
      code <- spotcore::desktop_product_safe_error_code_v1(error)
      reader <- data_statement_reader_message_v1(as.character(code), shiny::isolate(securities_import_result())$review$adapter$label, "Es wurde nichts gebucht.")
      securities_import_message(if (!is.null(reader)) list(tone = "error", title = reader$title, copy = reader$copy)
                                else list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1(code)))
    })
  # Pruefstand (rc.380): Haekchen nur, solange die Pruefung einen ungeprueften Leser nennt; ohne es kein Buchungsplan.
  securities_import_reader_ack_missing <- function() {
    check <- shiny::isolate(securities_import_result())$reader_check
    if (!data_statement_reader_check_required_v1(check) || isTRUE(shiny::isolate(input$securities_import_reader_ack))) return(FALSE)
    shiny::showNotification("Bitte erst die Vorschau mit den Belegen vergleichen und das Häkchen setzen. Es wurde nichts gebucht.", type = "warning", duration = 8)
    TRUE
  }
  # Depot-Zuordnungen gelten fuer die ganze Sitzung: Der Handle haengt nur an Aussteller und Depotnummer, eine neue
  # Datei- oder Ordnerauswahl muss ein schon zugeordnetes Depot also nicht erneut zuordnen. Ein ausdruecklich geleertes Feld hebt
  # die gemerkte Zuordnung auf.
  securities_import_remembered_depots <- shiny::reactiveVal(list())
  securities_import_depot_values <- function(result) {
    depots <- if (is.null(result) || is.null(result$suggestion)) list() else result$suggestion$depots
    values <- shiny::isolate(securities_import_remembered_depots())
    for (index in seq_along(depots)) {
      chosen <- input[[sprintf("securities_import_depot_%03d", index)]]
      handle <- depots[[index]]$depot_handle
      if (is.character(chosen) && length(chosen) == 1L && nzchar(chosen) && !is.null(result$account_refs[[chosen]])) values[[handle]] <- result$account_refs[[chosen]]
      else if (identical(chosen, "")) values[[handle]] <- NULL
    }
    values
  }
  # Dateien oder Ordner: gilt die zuletzt getroffene Auswahl.
  securities_import_selection <- shiny::reactiveVal(NULL)
  # Ueberspringen (#551) gilt fuer die gewaehlten Belege; eine neue Auswahl fragt neu (Festlegung 11.11.2026: kein Merken).
  securities_import_scope_skip <- shiny::reactiveVal(FALSE)
  shiny::observeEvent(securities_import_selection(), securities_import_scope_skip(FALSE), ignoreNULL = FALSE)
  securities_import_run_review <- function(depot_accounts = list(), note = NULL) {
    files <- securities_import_selection()
    if (is.null(files) || !nrow(files)) {
      securities_import_message(list(tone = "error", title = "Keine Belege gewählt", copy = "Bitte zuerst PDF-Abrechnungen oder einen Ordner auswählen.")); return(invisible(NULL))
    }
    window <- data_securities_statement_window_v1(input$securities_import_window, input$securities_import_from, input$securities_import_through)
    securities_import_safe(securities_statement_service$review(input$securities_import_adapter, files$datapath, files$name, depot_accounts, window,
                                                               scope_skip = securities_import_scope_skip()), function(result) {
      remembered <- depot_accounts; for (handle in names(result$depot_accounts)) remembered[[handle]] <- result$depot_accounts[[handle]]
      securities_import_remembered_depots(remembered)
      securities_import_result(result); message <- data_securities_statement_state_v1(result)
      if (!is.null(note)) message$copy <- paste(note, message$copy)
      securities_import_message(message)
    })
  }
  # "Fehlendes Asset anlegen" (#453): je fehlendem Asset einmal. Der Knopf fuehrt in die Neuanlage der Stammdaten, traegt ein, was der
  # Beleg nennt, und startet die Suche beim Kursanbieter mit der ISIN. Nach dem Anlegen geht es zurueck zum Import; die gewaehlten
  # Dateien bleiben, die Pruefung laeuft erneut.
  asset_center_new_prefill <- shiny::reactiveVal(NULL)
  securities_import_return <- shiny::reactiveVal(NULL)
  # Nach dem Anlegen (#455): naechster Schritt Marktdaten, bei Fonds auch Steuer. Gilt, solange das neue Asset gewaehlt ist.
  asset_center_created <- shiny::reactiveVal(NULL)
  output$asset_center_next_step <- shiny::renderUI({
    created <- asset_center_created()
    if (is.null(created) || !identical(input$asset_center_asset, created$ref) || identical(input$asset_center_mode, "new")) return(NULL)
    data_asset_center_next_step_ui_v1(created)
  })
  shiny::observeEvent(input$asset_center_next_market, shiny::updateTabsetPanel(session, "asset_center_step", selected = "Marktdaten"))
  shiny::observeEvent(input$asset_center_next_tax, shiny::updateTabsetPanel(session, "asset_center_step", selected = "3 · Steuer"))
  # ISIN schon im Katalog (#448): Hinweis bei der Neuanlage, statt ein Duplikat anzulegen.
  output$asset_center_isin_duplicate <- shiny::renderUI({
    if (!identical(input$asset_center_mode, "new")) return(NULL)
    hit <- data_asset_center_isin_match_v1(asset_center_catalog(), input$asset_center_isin)
    if (is.null(hit)) return(NULL)
    shiny::div(portelyra_status_panel("ISIN schon im Katalog", sprintf("„%s“ trägt diese ISIN bereits. Statt neu anzulegen, dieses Asset wählen – eine doppelte ISIN nimmt der Katalog ohnehin nicht an.",
      hit$display_name), tone = "warning"), shiny::actionButton("asset_center_isin_duplicate_select", "Dieses Asset wählen", class = "btn-default"))
  })
  shiny::observeEvent(input$asset_center_isin_duplicate_select, {
    hit <- data_asset_center_isin_match_v1(asset_center_catalog(), input$asset_center_isin); if (is.null(hit)) return()
    asset_center_new_prefill(NULL); securities_import_return(NULL)
    shiny::updateRadioButtons(session, "asset_center_mode", selected = "existing")
    asset_center_select(hit$ref)
  })
  asset_center_prefill_fields <- function(item) {
    text <- function(value) if (is.character(value) && length(value) == 1L && !is.na(value)) value else ""
    shiny::updateRadioButtons(session, "asset_center_domain", selected = "non_cash")
    shiny::updateTextInput(session, "asset_center_name", value = text(item$name))
    shiny::updateTextInput(session, "asset_center_isin", value = text(item$isin))
    # Die Art der Vorbelegung bleibt waehlbar, auch wenn das Portfolio ihre Klasse nicht waehlt (#542).
    asset_center_type_keep(if (nzchar(text(item$asset_type))) item$asset_type else NULL)
    if (nzchar(text(item$asset_type))) shiny::updateSelectInput(session, "asset_center_type", selected = item$asset_type)
    if (nzchar(text(item$currency))) shiny::updateTextInput(session, "asset_center_currency", value = item$currency)
    if (!is.null(item$quantity_scale)) shiny::updateSelectInput(session, "asset_center_scale", selected = as.character(item$quantity_scale))
    shiny::updateTextInput(session, "asset_center_provider_query", value = data_asset_center_prefill_query_v1(item))
    shiny::updateSelectInput(session, "asset_center_provider_search_mode", selected = data_asset_center_prefill_mode_v1(item))
  }
  output$securities_import_missing_ui <- shiny::renderUI(data_securities_statement_missing_ui_v1(securities_import_result()))
  # Kennungen nachtragen (#458 Teil 3, #439): gebuchte Vorgaenge, deren Beleg eine Kennung nennt, die im Beleg-Speicher fehlt.
  output$securities_import_references_ui <- shiny::renderUI(data_securities_statement_references_ui_v1(securities_import_result()))
  shiny::observeEvent(input$securities_import_references_run, {
    result <- securities_import_result()
    if (is.null(result) || is.null(result$trusted_review_token) || !isTRUE(as.integer(result$review$reference_backfill_count) > 0L)) return()
    if (!isTRUE(input$securities_import_references_confirm)) {
      securities_import_message(list(tone = "error", title = "Nicht bestätigt", copy = "Bitte zuerst bestätigen, dass die Kennungen aus den Belegen übernommen werden sollen.")); return()
    }
    securities_import_safe(securities_statement_service$references(result$trusted_review_token, now_utc()), function(done) {
      shiny::updateCheckboxInput(session, "securities_import_references_confirm", value = FALSE)
      securities_import_run_review(securities_import_depot_values(result), note = sprintf("%d Kennung(en) aus den Belegen nachgetragen%s.",
        as.integer(done$recorded_count), if (as.integer(done$kept_count) > 0L) sprintf(", %d inzwischen schon vorhanden", as.integer(done$kept_count)) else ""))
    })
  })
  shiny::observeEvent(input$securities_import_missing_pick, {
    result <- securities_import_result(); index <- suppressWarnings(as.integer(input$securities_import_missing_pick))
    missing <- if (is.null(result) || is.null(result$review$missing_assets)) list() else result$review$missing_assets
    if (length(index) != 1L || is.na(index) || index < 1L || index > length(missing)) return()
    item <- missing[[index]]
    asset_center_new_prefill(item); securities_import_return(list(import_kind = input$import_kind))
    shiny::updateTabsetPanel(session, "asset_center_step", selected = "1 · Stammdaten"); shiny::updateTabsetPanel(session, "master_section", selected = "assets")
    if (identical(input$asset_center_mode, "new")) asset_center_prefill_fields(item) else shiny::updateRadioButtons(session, "asset_center_mode", selected = "new")
    state(list(tone = "neutral", title = "Fehlendes Asset anlegen", copy = paste0("Vorbelegt aus dem Beleg: ", data_securities_statement_missing_label_v1(item),
      ". Art und Kurswährung prüfen – die Suche beim Kursanbieter schlägt sie vor –, dann „Asset anlegen und fortfahren“; danach geht es zurück zum Import.")))
  })
  # Vorhandenes zuordnen (#537): das gleichnamige Asset ohne ISIN waehlen und die ISIN aus dem Beleg vorbelegen; nachgetragen wird
  # mit „Stammdaten-Korrektur prüfen“ und Bestaetigung (eigener Befehl, die Kursfreigabe bleibt gueltig), danach zurueck zum Import.
  asset_center_pending_isin <- shiny::reactiveVal(NULL)
  shiny::observeEvent(input$securities_import_missing_assign, {
    result <- securities_import_result(); parts <- suppressWarnings(as.integer(strsplit(as.character(input$securities_import_missing_assign), "|", fixed = TRUE)[[1L]]))
    missing <- if (is.null(result) || is.null(result$review$missing_assets)) list() else result$review$missing_assets
    if (length(parts) != 2L || anyNA(parts) || parts[[1L]] < 1L || parts[[1L]] > length(missing)) return()
    item <- missing[[parts[[1L]]]]; labels <- as.character(unlist(item$existing_labels))
    if (parts[[2L]] < 1L || parts[[2L]] > length(labels) || !is.character(item$isin) || !nzchar(item$isin)) return()
    catalog <- asset_center_catalog()
    if (is.null(catalog)) { invisible(tryCatch(asset_center_autoload(reuse = TRUE), error = function(error) NULL)); catalog <- asset_center_catalog() }
    hit <- Filter(function(row) identical(row$display_name, labels[[parts[[2L]]]]) && (is.null(row$isin) || !nzchar(row$isin)), if (is.list(catalog)) catalog$assets else list())
    if (length(hit) != 1L) return(state(list(tone = "warning", title = "Nicht eindeutig", copy = sprintf("„%s“ ist im Katalog nicht eindeutig ohne ISIN zu finden.", labels[[parts[[2L]]]]))))
    securities_import_return(list(import_kind = input$import_kind)); asset_center_new_prefill(NULL)
    asset_center_pending_isin(list(ref = hit[[1L]]$ref, isin = toupper(item$isin)))
    shiny::updateTabsetPanel(session, "asset_center_step", selected = "1 · Stammdaten"); shiny::updateTabsetPanel(session, "master_section", selected = "assets")
    shiny::updateRadioButtons(session, "asset_center_mode", selected = "existing")
    if (identical(input$asset_center_asset, hit[[1L]]$ref)) { shiny::updateTextInput(session, "asset_center_edit_isin", value = toupper(item$isin)); asset_center_pending_isin(NULL) }
    else asset_center_select(hit[[1L]]$ref)
    state(list(tone = "neutral", title = "Vorhandenes Asset zuordnen", copy = paste0("„", hit[[1L]]$display_name, "“ ist gewählt, die ISIN ", toupper(item$isin),
      " aus dem Beleg vorbelegt. „Stammdaten-Korrektur prüfen“, bestätigen und ausführen – die Kursfreigabe bleibt gültig; danach geht es zurück zum Import.")))
  })
  # Wer selbst zurueck in die Transaktionen wechselt, bricht die Rueckkehr ab; die Vorbelegung verfaellt mit.
  shiny::observeEvent(input$asset_center_step, {
    if (identical(input$asset_center_step, "transactions") && !is.null(shiny::isolate(securities_import_return()))) {
      securities_import_return(NULL); asset_center_new_prefill(NULL)
    }
    if (identical(input$asset_center_step, "transactions")) securities_import_source_return(NULL)
  }, ignoreInit = TRUE)
  # `created`: das neu angelegte Asset (ref, name, type, valuation) - dann folgt die Kursquelle (#537); beim Zuordnen eines
  # vorhandenen Assets (ISIN nachgetragen) bleibt dessen Kursquelle, wie sie ist. Mehrere neue Assets eines Imports (#538): Jedes
  # bleibt in der Liste, bis es eine gepruefte Kursquelle hat. Gemerkt wird die interne Kennung - die Refs verschieben sich.
  securities_import_pending_sources <- shiny::reactiveVal(list())
  securities_import_source_return <- shiny::reactiveVal(NULL)
  securities_import_asset_ref_of <- function(asset_id) {
    hit <- names(Filter(function(row) identical(row$asset_id, asset_id), asset_center_catalog_editor$catalog$maps$asset))
    if (length(hit) == 1L) hit[[1L]] else NULL
  }
  securities_import_open_sources <- shiny::reactive({
    core <- asset_center_catalog(); providers <- asset_center_provider_catalog()
    data_securities_statement_open_sources_v1(securities_import_pending_sources(), if (is.list(core)) core$assets else list(),
      if (is.list(providers)) providers$mappings else list(), securities_import_asset_ref_of)
  })
  securities_import_return_after_create <- function(created = NULL) {
    back <- securities_import_return(); if (is.null(back)) return(invisible(NULL))
    securities_import_return(NULL); asset_center_new_prefill(NULL)
    shiny::updateTabsetPanel(session, "transactions_view", selected = "import")
    shiny::updateTabsetPanel(session, "asset_center_step", selected = "transactions")
    # Devisen bewertet die Wechselkurs-Historie, Cash braucht keinen Kurs, „nur Transaktionen“ und eigene Kurse keinen Anbieter:
    # Dort folgt kein Schritt.
    if (is.list(created) && !isTRUE(created$type %in% c("cash", "fx")) && (is.null(created$valuation) || identical(created$valuation, "external_market"))) {
      id <- tryCatch(desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", created$ref), error = function(error) NULL)
      if (is.character(id) && length(id) == 1L)
        securities_import_pending_sources(c(Filter(function(item) !identical(item$asset_id, id), shiny::isolate(securities_import_pending_sources())),
                                            list(list(asset_id = id, name = created$name))))
    }
    securities_import_run_review(securities_import_depot_values(securities_import_result()),
      note = if (is.list(created)) "Asset angelegt, Belege erneut geprüft." else "ISIN nachgetragen, Belege erneut geprüft.")
  }
  output$securities_import_next_step <- shiny::renderUI(data_securities_statement_sources_ui_v1(securities_import_open_sources()))
  shiny::observeEvent(input$securities_import_source_pick, {
    open <- securities_import_open_sources(); index <- suppressWarnings(as.integer(input$securities_import_source_pick))
    if (length(index) != 1L || is.na(index) || index < 1L || index > length(open)) return()
    item <- open[[index]]
    securities_import_source_return(list(asset_id = item$asset_id, name = item$name))
    asset_center_select(item$ref)
    shiny::updateTabsetPanel(session, "asset_center_step", selected = "Marktdaten"); shiny::updateTabsetPanel(session, "market_section", selected = "source")
  }, ignoreInit = TRUE)
  # Nach der Kursquelle zurueck zum Import (#538): sobald das Asset, fuer das man aus dem Import kam, eine gepruefte Kursquelle hat
  # oder nicht mehr ueber den Markt bewertet wird. Wer vorher selbst in die Transaktionen wechselt, bricht die Rueckkehr ab.
  shiny::observeEvent(securities_import_open_sources(), {
    back <- securities_import_source_return(); if (!is.list(back)) return()
    open <- securities_import_open_sources()
    if (any(vapply(open, function(item) identical(item$asset_id, back$asset_id), logical(1L)))) return()
    securities_import_source_return(NULL)
    shiny::updateTabsetPanel(session, "transactions_view", selected = "import")
    shiny::updateTabsetPanel(session, "asset_center_step", selected = "transactions")
    securities_import_message(data_securities_statement_source_done_v1(back$name, securities_import_result(), open))
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$securities_import_files, { securities_import_selection(input$securities_import_files); securities_import_result(NULL); securities_import_message(NULL) }, ignoreInit = TRUE)
  reference_backfill_area <- data_reference_backfill_server_v1(input, output, session, activity_reference_service, now_utc, archive_service = statement_archive_service,
    accounts = function() { model <- asset_center_catalog(); if (is.null(model)) list() else model$accounts },
    resolve_id = function(ref) desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "account", ref))
  # Das Institut, das "Im Import buchen" im Eingang vorgibt (#522).
  securities_import_archive_wanted <- shiny::reactiveVal(NULL)
  data_statement_archive_source_server_v1(input, output, session, "securities_import", statement_archive_service,
    on_take = function(frame) { securities_import_selection(frame); securities_import_result(NULL); securities_import_message(NULL) },
    accounts = function() { model <- asset_center_catalog(); if (is.null(model)) list() else model$accounts },
    resolve_id = function(ref) desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "account", ref),
    preselect = securities_import_archive_wanted)
  shiny::observeEvent(input$securities_import_folder, { securities_import_selection(input$securities_import_folder); securities_import_result(NULL); securities_import_message(NULL) }, ignoreInit = TRUE)
  shiny::observeEvent(input$securities_import_review, securities_import_run_review(securities_import_depot_values(securities_import_result())))
  # Leser je Importart (#449, #452): Wertpapiere, Krypto oder Devisen. Ein Wechsel der Art verwirft die Pruefung der anderen;
  # Rewards und Cash-Auszuege haben eigene Karten, dort bleibt die Auswahl der Belegkarte stehen.
  # Ausblenden (rc.381, Festlegung 09.11.2026): Die Import-Karten bieten nur Leser von Plugins an, die in mindestens einem
  # Portfolio aktiv sind; installierte Plugins kommen dazu. Gelesen beim Oeffnen des Reiters "Import" (dort wirken Aenderungen im Reiter
  # "Leser" sofort). Gesperrt wird je Portfolio beim Buchen.
  import_offered <- shiny::reactiveVal(NULL)
  import_offered_ids <- function() {
    offered <- shiny::isolate(import_offered())
    if (is.null(offered)) NULL else vapply(offered$readers, function(item) as.character(item$reader_id), character(1L))
  }
  # Die Leserliste einmal je Oeffnen des Reiters "Import" (import_offered_apply); wer vorher eine Auswahl braucht (Wechsel der Importart,
  # Sprung aus dem Eingang), laedt sie hier.
  import_offered_load <- function() {
    if (is.null(shiny::isolate(import_offered()))) import_offered(tryCatch(statement_reader_check_service$offered(), error = function(error) NULL))
    shiny::isolate(import_offered())
  }
  import_offered_choices <- function(domain) {
    offered <- import_offered_load()
    if (identical(domain, "reward")) desktop_reward_adapter_choices_v1(offered) else desktop_securities_import_adapter_choices_v1(domain, offered)
  }
  import_offered_filter_list <- function(adapters) {
    ids <- import_offered_ids(); if (is.null(ids) || is.null(adapters)) return(adapters)
    Filter(function(item) item$adapter_id %in% ids, adapters)
  }
  # Nur schreiben, wenn sich der Inhalt der Liste wirklich aendert (ausgeblendet oder installiert): Ein Neuschreiben setzt sonst eine
  # gerade getroffene Auswahl zurueck, wenn ein Klick mit dem Laden kreuzt (siehe auch #184).
  import_offered_written <- new.env(parent = emptyenv())
  import_offered_update <- function(id, choices, defaults) {
    last <- import_offered_written[[id]]
    if ((is.null(last) && identical(choices, defaults)) || identical(last, choices)) return(invisible(NULL))
    assign(id, choices, envir = import_offered_written)
    current <- shiny::isolate(input[[id]])
    shiny::updateSelectInput(session, id, choices = choices, selected = if (isTRUE(current %in% choices)) current else unname(choices)[[1L]])
  }
  import_offered_apply <- function() {
    import_offered(tryCatch(statement_reader_check_service$offered(), error = function(error) NULL))
    if (is.null(import_offered())) return(invisible(NULL))
    import_offered_update("securities_import_adapter", import_offered_choices(securities_import_domain), desktop_securities_import_adapter_choices_v1(securities_import_domain))
    import_offered_update("statement_exchange_adapter", import_offered_choices("reward"), desktop_reward_adapter_choices_v1())
    if (!is.null(shiny::isolate(cash_catalog()))) invisible(tryCatch(cash_import_populate(shiny::isolate(cash_catalog())), error = function(error) NULL))
    invisible(NULL)
  }
  shiny::observeEvent(input$transactions_view, { if (identical(input$transactions_view, "import")) import_offered_apply() }, ignoreInit = TRUE)
  securities_import_domain <- "securities"
  # Vom Eingang (#513) vorgegebener Leser: Er gilt beim naechsten Wechsel der Importart, statt des ersten der Liste.
  securities_import_pending_adapter <- NULL
  shiny::observeEvent(input$import_kind, {
    domain <- if (isTRUE(input$import_kind %in% c("fx", "crypto"))) input$import_kind else if (identical(input$import_kind, "securities")) "securities" else return()
    if (identical(domain, securities_import_domain)) return()
    securities_import_domain <<- domain
    choices <- import_offered_choices(domain)
    assign("securities_import_adapter", choices, envir = import_offered_written)
    pending <- securities_import_pending_adapter; securities_import_pending_adapter <<- NULL
    shiny::updateSelectInput(session, "securities_import_adapter", choices = choices, selected = if (isTRUE(pending %in% choices)) pending else unname(choices)[[1L]])
    securities_import_result(NULL); securities_import_message(NULL)
  }, ignoreInit = TRUE)
  # Monatlicher Eingang (#513): Ein Klick auf "Im Import buchen" oeffnet den Import der Art mit dem Leser des Rezepts.
  statement_intake_navigate <- function(kind, adapter, recipe = NULL) {
    # Zuerst die Leserliste (#486): Die Auswahl der Import-Karten kommt aus ihr; ohne sie gaebe es den Leser des Rezepts dort noch nicht.
    import_offered_apply()
    # Institut und, wo eindeutig, das Cash-Konto vorwaehlen (#522).
    model <- asset_center_catalog()
    pick <- data_statement_intake_preselection_v1(recipe, adapter, if (is.null(model)) list() else model$accounts)
    if (kind %in% c("securities", "crypto", "fx") && !is.null(pick$institution)) securities_import_archive_wanted(pick$institution)
    # Rewards (#520): Boerse des Lesers waehlen und das Institut in der Ablage vorgeben.
    if (identical(kind, "rewards")) {
      shiny::updateSelectInput(session, "statement_exchange_adapter", selected = adapter)
      if (!is.null(pick$institution)) statement_exchange_archive_wanted(pick$institution)
    }
    if (identical(kind, "cash") && !is.null(pick$cash_account)) {
      account_id <- tryCatch(desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "account", pick$cash_account$ref),
        error = function(error) NULL)
      selection <- tryCatch(.data_cash_coverage_selection(cash_editor, runtime$context), error = function(error) NULL)
      ref <- if (is.null(account_id) || is.null(selection)) NULL else selection$accounts$ref_by_id[[account_id]]
      if (!is.null(account_id)) cash_import_remembered$account <- account_id
      if (!is.null(ref)) shiny::updateSelectInput(session, "cash_import_account", selected = unname(ref))
    }
    shiny::updateTabsetPanel(session, "asset_center_step", selected = "transactions")
    shiny::updateTabsetPanel(session, "transactions_view", selected = "import")
    if (kind %in% c("securities", "crypto", "fx")) {
      if (identical(securities_import_domain, kind)) shiny::updateSelectInput(session, "securities_import_adapter", selected = adapter)
      else securities_import_pending_adapter <<- adapter
    }
    # Die Art des Rezepts bleibt waehlbar, auch wenn das Portfolio sie nicht anbietet (#542).
    import_kind_keep(kind)
    shiny::updateRadioButtons(session, "import_kind", selected = kind)
    if (identical(kind, "cash")) shiny::updateSelectInput(session, "cash_import_adapter", selected = adapter)
    if (identical(kind, "rewards")) shiny::updateSelectInput(session, "statement_exchange_adapter", selected = adapter)
  }
  statement_intake_area <- data_statement_intake_server_v1(input, output, session, statement_archive_service,
    accounts = function() { model <- asset_center_catalog(); if (is.null(model)) list() else model$accounts },
    resolve_id = function(ref) desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "account", ref),
    navigate = statement_intake_navigate, choose_folder = data_statement_intake_choose_folder_v1,
    active = shiny::reactive(identical(input$asset_center_step, "transactions") && identical(input$transactions_view, "intake")))
  output$securities_import_scope_ui <- shiny::renderUI(data_securities_statement_scope_ui_v1(securities_import_result()$review,
    open_settings = data_settings_open_target_js_v1("portfolio-configuration-change")))
  shiny::observeEvent(input$securities_import_scope_skip, {
    securities_import_scope_skip(TRUE)
    securities_import_run_review(securities_import_depot_values(securities_import_result()), note = "Buchungen der nicht gewählten Klasse übersprungen. Erneut geprüft:")
  })
  shiny::observeEvent(input$securities_import_scope_unskip, {
    securities_import_scope_skip(FALSE)
    securities_import_run_review(securities_import_depot_values(securities_import_result()), note = "Nicht mehr übersprungen. Erneut geprüft:")
  })
  shiny::observeEvent(input$securities_import_scope_add, {
    result <- securities_import_result(); review <- result$review
    keys <- unique(vapply(c(review$out_of_scope_classes, review$out_of_scope_outside_window), function(item) as.character(item$key), character(1L)))
    # Der Umfang in den Einstellungen gilt fuer das in "Assets pflegen" gewaehlte Portfolio: nur vorankreuzen, wenn es das des Imports ist.
    target <- tryCatch(jsonlite::fromJSON(result$trusted_review_token, simplifyVector = FALSE)$portfolio_id, error = function(error) NULL)
    shown <- portfolio_configuration$portfolio()
    if (!is.list(shown) || !identical(shown$portfolio_id, target)) {
      securities_import_message(list(tone = "warning", title = "Anderes Portfolio gewählt", copy = paste0("„Umfang dieses Portfolios“ zeigt das oben in",
        " „Assets pflegen“ gewählte Portfolio", if (is.list(shown)) paste0(" „", shown$label, "“") else "", ". Dieser Import bucht in „",
        review$scope_portfolio_label %||% "–", "“ – bitte dort zuerst dieses Portfolio wählen.")))
      return()
    }
    portfolio_configuration$request_classes(setdiff(keys, "cash"))
  })
  # Nach "Uebernehmen" im Umfang prueft der Import von selbst neu, wenn er Vorgaenge einer nicht gewaehlten Klasse hatte.
  shiny::observeEvent(portfolio_configuration$asset_types(), {
    review <- shiny::isolate(securities_import_result())$review
    if (is.list(review) && (isTRUE(as.integer(review$out_of_scope_count) > 0L) || isTRUE(as.integer(review$out_of_scope_outside_window_count) > 0L) ||
                            isTRUE(as.integer(review$scope_skipped_count) > 0L)))
      securities_import_run_review(securities_import_depot_values(shiny::isolate(securities_import_result())), note = "Umfang geändert. Erneut geprüft:")
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$securities_import_prepare, {
    result <- securities_import_result()
    # Pflichtwahl (#551): erst entscheiden, dann vorbereiten - der Kern weist den Buchungsschritt ohne Wahl ohnehin ab.
    if (is.list(result$review) && isTRUE(as.integer(result$review$out_of_scope_count) > 0L)) {
      securities_import_message(list(tone = "warning", title = "Erst entscheiden", copy = paste(result$review$out_of_scope_count,
        "Buchung(en) gehören zu einer nicht gewählten Klasse: oben „Klasse dazunehmen“ oder „Diese Buchungen überspringen“ wählen."))); return()
    }
    if (is.null(result) || is.null(result$review) || as.integer(result$review$new_count) < 1L) {
      securities_import_message(list(tone = "error", title = "Nichts vorzubereiten", copy = "Erst „Belege prüfen“ – vorbereitet werden nur neue Vorgänge.")); return()
    }
    if (securities_import_reader_ack_missing()) return()
    securities_import_safe({
      directory <- tempfile("portelyra-wp-belege-"); dir.create(directory, mode = "0700"); target <- file.path(directory, "belege.csv")
      securities_statement_service$csv(result$trusted_review_token, target, reader_check_acknowledged = isTRUE(input$securities_import_reader_ack))
      portfolio_id <- jsonlite::fromJSON(result$trusted_review_token, simplifyVector = FALSE)$portfolio_id
      data_asset_activity_csv_inspect_v1(activity_csv_center, runtime$context, target, portfolio_id)
    }, function(model) {
      activity_csv_inspection(model); activity_csv_preview(NULL)
      if (identical(model$status, "ready_for_preview")) {
        activity_csv_run_preview(model)
        preview <- activity_csv_preview()
        securities_import_message(if (!is.null(preview) && identical(preview$status, "ready_for_confirmation"))
          list(tone = "warning", title = "Vorschau bereit", copy = paste(preview$ready_row_count, "neue Buchung(en) wie in der Tabelle. Mit „Neue Vorgänge buchen“ werden genau diese gebucht."))
          else list(tone = "error", title = "Vorschau blockiert", copy = data_securities_import_blocked_copy_v1(preview)))
        return()
      }
      # Gebucht wird ueber den CSV-Import: Die Wiederaufnahme steht unter "Manuell" und erscheint jetzt von selbst (#492).
      tryCatch(activity_csv_resume_offer(data_asset_activity_csv_resumable_v1(activity_csv_center, runtime$context)), error = function(error) NULL)
      securities_import_message(list(tone = "warning", title = "Vorschau nicht möglich", copy = if (identical(model$status, "resumable"))
        "Diese Vorgänge wurden schon einmal bestätigt, aber nicht vollständig gebucht. Bitte unter „Manuell“ → „Unterbrochenen Import fortsetzen“ abschließen."
        else "Diese Vorgänge stehen schon in einem anderen, unterbrochenen Import. Bitte ihn zuerst fortsetzen."))
    })
  })
  shiny::observeEvent(input$securities_import_execute, {
    preview <- activity_csv_preview()
    if (is.null(preview) || !identical(preview$status, "ready_for_confirmation")) {
      securities_import_message(list(tone = "error", title = "Nichts zu buchen", copy = "Erst „Neue Vorgänge vorbereiten“ – gebucht wird nur eine geprüfte Vorschau.")); return()
    }
    if (securities_import_reader_ack_missing()) return()
    acknowledged <- isTRUE(input$securities_import_reader_ack)
    activity_csv_execute_run(function(result) {
      # Geprueft und gebucht: der Pruefstand des Lesers waechst mit (#450). Gebucht ist schon - ein Fehler hier
      # darf die Rueckmeldung nicht verdecken, die erneute Pruefung zeigt dann den alten Stand.
      token <- securities_import_result()$trusted_review_token
      confirmed <- if (is.character(token) && length(token) == 1L) tryCatch(securities_statement_service$confirm(token, result$created_event_count, now_utc(), acknowledged),
        error = function(error) list(provenance_status = paste0("failed:", if (is.null(error$code)) "confirm_failed" else error$code))) else NULL
      # Herkunft je Buchung (rc.378): ein Fehler beim Festhalten steht in der Meldung, die Buchungen bleiben.
      provenance <- if (is.character(result$provenance_status) && startsWith(result$provenance_status, "failed")) result$provenance_status
        else if (is.list(confirmed) && is.character(confirmed$provenance_status)) confirmed$provenance_status else ""
      securities_import_run_review(securities_import_depot_values(securities_import_result()),
        note = paste(Filter(nzchar, c(paste0(result$created_event_count, " Buchung(en) aus Belegen gespeichert."), data_statement_provenance_note_v1(provenance),
                                      data_statement_reader_check_note_v1(if (is.list(confirmed)) confirmed$reader_check_recorded else NULL),
                                      "Erneut geprüft:")), collapse = " "))
    })
  })
  # Pruefstand (rc.380): Hinweis und Haekchen haengen nur an der Pruefung, nicht an den Meldungen - so bleibt das Haekchen bis zum Buchen stehen.
  output$securities_import_reader_check <- shiny::renderUI({
    check <- securities_import_result()$reader_check
    if (!is.list(check)) return(NULL)
    shiny::tagList(data_statement_reader_check_panel_v1(check), data_statement_reader_check_ack_v1("securities_import_reader_ack", check))
  })
  output$securities_import_state <- shiny::renderUI({
    message <- securities_import_message()
    if (is.null(message)) return(portelyra_status_panel("Belege wählen", "Institut (oder „Automatisch erkennen“) und PDF-Abrechnungen wählen, dann „Belege prüfen“. Die Prüfung schreibt nichts.", tone = "neutral"))
    portelyra_status_panel(message$title, message$copy, tone = message$tone)
  })
  # Leserregister nur bei Bedarf laden: beim Start steht die Auswahl auf "Automatisch erkennen", kein Python-Aufruf.
  securities_import_adapters <- local({ cache <- NULL; function() { if (is.null(cache)) cache <<- securities_statement_service$adapters(); cache } })
  output$securities_import_adapter_info <- shiny::renderUI({
    result <- securities_import_result(); chosen <- input$securities_import_adapter
    adapter <- if (!is.null(result) && !is.null(result$review$adapter)) result$review$adapter
      else if (is.character(chosen) && length(chosen) == 1L && !identical(chosen, "auto"))
        tryCatch(Filter(function(item) identical(item$adapter_id, chosen), securities_import_adapters())[[1L]], error = function(error) NULL)
    data_securities_statement_adapter_info_v1(adapter, if (is.null(adapter) && identical(chosen, "auto")) tryCatch(securities_import_adapters(), error = function(error) NULL))
  })
  output$securities_import_depots <- shiny::renderUI({
    result <- securities_import_result()
    depots <- if (is.null(result) || is.null(result$suggestion)) list() else result$suggestion$depots
    if (!length(depots)) return(NULL)
    accounts <- result$suggestion$accounts
    choices <- c("Bitte zuordnen" = "", stats::setNames(vapply(accounts, `[[`, character(1L), "account_ref"),
      vapply(accounts, function(item) if (nzchar(item$institution)) paste(item$label, "·", item$institution) else item$label, character(1L))))
    chosen <- result$depot_accounts
    shiny::div(class = "pl-form-grid", lapply(seq_along(depots), function(index) {
      depot <- depots[[index]]
      account_id <- chosen[[depot$depot_handle]]
      selected <- if (is.null(account_id)) "" else names(Filter(function(value) identical(value, account_id), result$account_refs))[1L]
      shiny::selectInput(sprintf("securities_import_depot_%03d", index), paste0(if (depot$profile %in% c("smartbroker_fx", "crypto")) "" else "Depot ", depot$depot_mask,
        if (identical(depot$profile, "crypto")) "" else paste0(" · ", depot$profile_label), " (", depot$candidate_count, " Vorgänge)",
        if (isTRUE(depot$learned)) " · erkannt an gebuchten Kennungen" else ""),
        choices = choices, selected = if (is.na(selected)) "" else selected)
    }))
  })
  output$securities_import_rows <- shiny::renderTable(data_securities_statement_rows_frame_v1(securities_import_result()), striped = TRUE, bordered = TRUE)
  # Vorabpauschalen der Belege (#460, #471): eigene Tabelle und eigene Bestaetigung; sie landen im Vorabpauschalen-Speicher, nicht im Bestand.
  output$securities_import_advance_ui <- shiny::renderUI({
    result <- securities_import_result()
    frame <- data_securities_statement_advance_frame_v1(result)
    if (is.null(frame)) return(NULL)
    review <- result$review
    new_count <- as.integer(review$advance_lump_sum_new_count); differing <- as.integer(review$advance_lump_sum_differing_count)
    shiny::div(class = "pl-section",
      shiny::h4("Vorabpauschalen aus den Belegen"),
      shiny::p(class = "pl-section-copy", "Je Fonds, Konto und Berechnungsjahr gegen die eingetragenen Werte (Daten → „Steuer“) geprüft. Betrag vor Teilfreistellung, wie ihn die Bank nennt."),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("securities_import_advance_rows")),
      if (differing > 0L) shiny::checkboxInput("securities_import_advance_replace", paste0("Abweichende Werte (", differing, ") durch den Belegwert ersetzen"), value = FALSE),
      if (new_count + differing > 0L) shiny::div(class = "pl-editor-actions",
        shiny::actionButton("securities_import_advance_record", "Vorabpauschalen übernehmen", class = "btn-primary")))
  })
  output$securities_import_advance_rows <- shiny::renderTable(data_securities_statement_advance_frame_v1(securities_import_result()), striped = TRUE, bordered = TRUE)
  shiny::observeEvent(input$securities_import_advance_record, {
    result <- securities_import_result()
    token <- if (is.null(result)) NULL else result$trusted_review_token
    replace <- isTRUE(input$securities_import_advance_replace)
    pending <- if (is.null(result)) 0L else as.integer(result$review$advance_lump_sum_new_count) + if (replace) as.integer(result$review$advance_lump_sum_differing_count) else 0L
    if (!is.character(token) || pending < 1L) {
      securities_import_message(list(tone = "error", title = "Nichts zu übernehmen", copy = "Neue Vorabpauschalen gibt es nicht; abweichende werden nur mit gesetztem Häkchen ersetzt.")); return()
    }
    if (securities_import_reader_ack_missing()) return()
    securities_import_safe(securities_statement_service$advance_lump_sums(token, replace, now_utc(), isTRUE(input$securities_import_reader_ack)), function(recorded) {
      tryCatch(advance_lump_sum$read(), error = function(error) NULL)
      securities_import_run_review(securities_import_depot_values(securities_import_result()),
        note = paste0(recorded$written_count, " Vorabpauschale(n) eingetragen", if (replace) " (abweichende ersetzt)" else "", ". Erneut geprüft:"))
    })
  })
  # Splitmitteilungen der Belege (#451, rc.372): eigene Tabelle und eigene Bestaetigung. Der Split landet im Split-Speicher;
  # split-bereinigt gebuchte Vorgaenge davor bekommen je eine Korrektur mit Stueckzahl und Kurs ihres Belegs.
  output$securities_import_split_ui <- shiny::renderUI({
    result <- securities_import_result()
    splits <- data_securities_statement_split_frame_v1(result)
    conversions <- data_securities_statement_conversion_frame_v1(result)
    if (is.null(splits) && is.null(conversions)) return(NULL)
    action <- data_securities_statement_split_action_v1(result$review)
    shiny::div(class = "pl-section",
      shiny::h4("Kapitalmaßnahmen aus den Belegen"),
      shiny::p(class = "pl-section-copy", paste("Ein Split wird unter Stammdaten → Kapitalmaßnahmen gespeichert; der FIFO-Stand teilt die Lots am Stichtag.",
        "Split-bereinigt gebuchte Vorgänge davor bekommen Stückzahl und Kurs ihres Belegs, je als Korrektur – der Vorgänger bleibt erhalten.",
        "Gewinne, Einstand und Bestand bleiben gleich. Je Vorgang dauert das einige Sekunden.")),
      if (!is.null(splits)) shiny::div(class = "pl-table-wrap", shiny::tableOutput("securities_import_split_rows")),
      if (!is.null(conversions)) shiny::tagList(shiny::h5("Umzustellende Vorgänge"),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("securities_import_conversion_rows"))),
      if (!is.null(action)) shiny::div(class = "pl-editor-actions", shiny::actionButton("securities_import_split_record", action, class = "btn-primary")))
  })
  output$securities_import_split_rows <- shiny::renderTable(data_securities_statement_split_frame_v1(securities_import_result()), striped = TRUE, bordered = TRUE)
  output$securities_import_conversion_rows <- shiny::renderTable(data_securities_statement_conversion_frame_v1(securities_import_result()), striped = TRUE, bordered = TRUE)
  shiny::observeEvent(input$securities_import_split_record, {
    result <- securities_import_result()
    token <- if (is.null(result)) NULL else result$trusted_review_token
    if (!is.character(token) || is.null(data_securities_statement_split_action_v1(result$review))) {
      securities_import_message(list(tone = "error", title = "Nichts zu übernehmen", copy = "Erst „Belege prüfen“; übernommen wird nur, was die Prüfung als neu oder umstellbar zeigt.")); return()
    }
    if (securities_import_reader_ack_missing()) return()
    recorded <- tryCatch(securities_statement_service$stock_splits(token, now_utc(), isTRUE(input$securities_import_reader_ack)), error = function(error) error)
    if (inherits(recorded, "error")) {
      code <- tryCatch(recorded$code, error = function(condition) NULL)
      securities_import_message(data_securities_statement_split_message_v1(code = if (is.character(code) && length(code) == 1L) code else "desktop_product_boundary_failed"))
      # Teilweise Gebuchtes zeigt die naechste Pruefung; der FIFO-Stand folgt ihm trotzdem.
      update_realized_state("incremental", tolerate_failure = TRUE)
      return()
    }
    materialized <- update_realized_state("incremental", tolerate_failure = TRUE)
    published <- if (is.null(materialized) || is.null(portfolio_history_service)) NULL else
      tryCatch({ value <- portfolio_history_service$history_publish(now_utc()); if (is.list(value) && value$status %in% c("published", "already_published")) "published" else NULL },
               error = function(error) NULL)
    tryCatch({ refresh_activity_catalog(); refresh_activity_corrections() }, error = function(error) NULL)
    securities_import_run_review(securities_import_depot_values(securities_import_result()),
      note = data_securities_statement_split_message_v1(recorded, published = published)$copy)
  })
  # "Im Editor öffnen" (#454): einen offenen Vorgang in die Maske "Transaktionen manuell erfassen" uebernehmen - gebucht wird erst dort.
  output$securities_import_open_editor_ui <- shiny::renderUI({
    choices <- data_securities_statement_open_choices_v1(securities_import_result())
    if (!length(choices)) return(NULL)
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("securities_import_open_pick", "Offener Vorgang", choices = choices),
      shiny::actionButton("securities_import_open_editor", "Im Editor öffnen", class = "btn-default",
        `aria-controls` = "asset-activity-editor-anchor",
        onclick = paste0("window.setTimeout(function(){var target=document.getElementById('asset-activity-editor-anchor');",
                         "if(target){target.scrollIntoView({behavior:'smooth',block:'start'});target.focus({preventScroll:true});}},600);")))
  })
  securities_import_editor_prefill <- shiny::reactiveVal(NULL)
  shiny::observeEvent(input$securities_import_open_editor, {
    result <- securities_import_result()
    token <- if (is.null(result)) NULL else result$trusted_review_token
    open_rows <- if (is.null(token)) list() else jsonlite::fromJSON(token, simplifyVector = FALSE)$open_rows
    picked <- suppressWarnings(as.integer(input$securities_import_open_pick))
    row <- Filter(function(item) identical(as.integer(item$candidate_ordinal), picked), if (is.null(open_rows)) list() else open_rows)
    if (!length(row)) { securities_import_message(list(tone = "error", title = "Kein offener Vorgang gewählt", copy = "Erst „Belege prüfen“, dann einen offenen Vorgang wählen.")); return() }
    row <- row[[1L]]
    # Wie beim Asset-Wechsel: eine ausgewaehlte Buchung oder eingegebene Betraege werden nicht ueberschrieben.
    entered <- any(vapply(list(input$activity_quantity, input$activity_unit_price, input$activity_gross_total, input$activity_monetary_fee, input$activity_asset_fee),
      function(value) is.character(value) && length(value) == 1L && !is.na(value) && nzchar(trimws(value)), logical(1L)))
    if (length(workflow_refs()) > 0L || entered) {
      securities_import_message(list(tone = "warning", title = "Maske nicht frei", copy = if (length(workflow_refs()) > 0L)
        "In der Maske ist eine Buchung ausgewählt – erst die Auswahl leeren, dann erneut „Im Editor öffnen“." else
        "In der Maske stehen schon Beträge – erst „Eingaben verwerfen“, dann erneut „Im Editor öffnen“."))
      return()
    }
    securities_import_safe({
      center_ref <- names(Filter(function(item) identical(item$asset_id, row$asset_id), asset_center_catalog_editor$catalog$maps$asset))
      if (length(center_ref) != 1L) stop("Der Coin steht nicht im Asset-Center.", call. = FALSE)
      asset_center_select(center_ref); asset_center_selected_ref <<- center_ref
      refresh_activity_catalog(reuse = TRUE)
      asset_ref <- data_asset_activity_editor_ref_for_internal_v1(activity_editor, runtime$context, "asset", row$asset_id)
      account_ref <- data_asset_activity_editor_ref_for_internal_v1(activity_editor, runtime$context, "account", row$account_id)
      form <- data_securities_statement_editor_form_v1(row, asset_ref, account_ref)
      accounts <- choice_vector(activity_catalog()$accounts)
      shiny::updateSelectInput(session, "activity_type", selected = form$event_type)
      activity_asset_update(selected = form$asset_ref)
      shiny::updateSelectInput(session, "activity_account", choices = accounts, selected = form$account_ref)
      shiny::updateSelectInput(session, "activity_related_account", choices = accounts, selected = form$related_account_ref)
      shiny::updateSelectInput(session, "activity_time_evidence", selected = "exact")
      shiny::updateDateInput(session, "activity_date", value = as.Date(form$local_date))
      shiny::updateTextInput(session, "activity_time", value = form$local_time); shiny::updateTextInput(session, "activity_zone", value = form$time_zone)
      shiny::updateTextInput(session, "activity_utc", value = "")
      shiny::updateTextInput(session, "activity_quantity", value = form$quantity); shiny::updateTextInput(session, "activity_asset_fee", value = form$asset_fee)
      if (nzchar(form$amount_mode)) {
        shiny::updateSelectInput(session, "activity_amount_mode", selected = form$amount_mode); shiny::updateSelectInput(session, "activity_basis_mode", selected = "derived_trade")
        shiny::updateTextInput(session, "activity_unit_price", value = form$unit_price); shiny::updateTextInput(session, "activity_monetary_fee", value = form$monetary_fee)
      }
      form
    }, function(form) {
      securities_import_editor_prefill(form)
      state(list(tone = "warning", title = "Aus dem Krypto-Import vorbelegt", copy = paste("Noch nichts gebucht.", form$hint, "Dann wie gewohnt prüfen und buchen.")))
      securities_import_message(list(tone = "neutral", title = "Im Editor vorbelegt", copy = paste("Die Maske „Transaktionen manuell erfassen“ ist gefüllt –", form$hint)))
    })
  })
  output$securities_import_documents <- shiny::renderTable(data_securities_statement_documents_frame_v1(securities_import_result()), striped = TRUE, bordered = TRUE)
  output$securities_import_preview <- shiny::renderTable({
    preview <- activity_csv_preview(); if (is.null(preview) || is.null(securities_import_result())) return(NULL)
    data_asset_activity_csv_rows_frame_v1(preview)
  }, striped = TRUE, bordered = TRUE)
  # Fills the import selects from any loaded Cash catalog, whoever loaded it (#184 retest).
  # Browser refs are positional and shift when an asset or account is archived, so the
  # user's choice is remembered by internal ID and mapped to the new ref after a reload.
  cash_import_remembered <- new.env(parent = emptyenv())
  cash_import_remember <- function() {
    selection <- tryCatch(.data_cash_coverage_selection(cash_editor, runtime$context), error = function(error) NULL); if (is.null(selection)) return(invisible(NULL))
    id_of <- function(area, ref, field) { row <- if (is.character(ref) && length(ref) == 1L && nzchar(ref)) selection[[area]]$by_ref[[ref]] else NULL; if (is.null(row)) NULL else row[[field]] }
    cash_import_remembered$account <- id_of("accounts", input$cash_import_account, "account_id")
    cash_import_remembered$movements <- id_of("accounts", input$cash_movements_account, "account_id")
    cash_import_remembered$asset <- id_of("assets", input$cash_import_asset, "asset_id")
    invisible(NULL)
  }
  shiny::observeEvent(list(input$cash_import_account, input$cash_import_asset, input$cash_movements_account), cash_import_remember(), ignoreInit = TRUE)
  cash_import_adapter_list <- shiny::reactiveVal(NULL)
  # Anzeigename eines Lesers fuer Meldungen (#486): aus der geladenen Auswahl, sonst die Kennung.
  cash_statement_reader_label <- function(adapter_id) {
    adapters <- shiny::isolate(cash_import_adapter_list())
    hit <- if (is.null(adapters)) list() else Filter(function(item) identical(item$adapter_id, adapter_id), adapters)
    if (length(hit)) as.character(hit[[1L]]$label) else if (is.null(adapter_id)) "" else as.character(adapter_id)
  }
  cash_import_populate <- function(model) {
    selection <- tryCatch(.data_cash_coverage_selection(cash_editor, runtime$context), error = function(error) NULL)
    ref_for <- function(area, id) if (is.null(id) || is.null(selection)) "" else { ref <- selection[[area]]$ref_by_id[[id]]; if (is.null(ref)) "" else unname(ref) }
    keep <- function(value, refs, fallback = "") if (is.character(value) && length(value) == 1L && value %in% refs) value else fallback
    # Only rewrite a list whose content really changed: a reload that races with the user's
    # click would otherwise overwrite the fresh choice (#184 retest).
    update <- function(id, choices, selected) {
      signature <- paste(names(choices), unname(choices), collapse = "\r")
      if (identical(cash_import_remembered[[paste0("signature_", id)]], signature)) return(invisible(NULL))
      cash_import_remembered[[paste0("signature_", id)]] <- signature
      shiny::updateSelectInput(session, id, choices = choices, selected = selected)
    }
    # Nur Cash- und Bankkonten (#492): Ein Auszug eines Fremdwaehrungskontos (Devisen sind Assets) oder eines Depots wuerde sonst als
    # Cash gebucht - ein Leser kann auch Auszuege von Fremdwaehrungskonten erkennen.
    accounts <- Filter(function(row) isTRUE(row$account_type %in% c("cash", "bank")), model$accounts)
    # Ein ruhendes Konto (#529 Punkt 1) bietet der Import nicht an; die Bewegungsliste zeigt es weiter.
    resting <- data_resting_account_ids_v1(statement_archive_service)
    importable <- if (!length(resting) || is.null(selection)) accounts else Filter(function(row) {
      account <- tryCatch(.data_cash_coverage_resolve(selection, "accounts", row$ref), error = function(error) NULL)
      is.null(account) || !account$account_id %in% resting
    }, accounts)
    account_refs <- vapply(importable, `[[`, character(1L), "ref")
    update("cash_import_account", choice_vector(importable), keep(ref_for("accounts", cash_import_remembered$account), account_refs))
    account_refs <- vapply(accounts, `[[`, character(1L), "ref")
    update("cash_movements_account", c("Alle Cash-Konten" = "", choice_vector(accounts)[-1L]), keep(ref_for("accounts", cash_import_remembered$movements), account_refs))
    assets <- model$cash_assets; asset_refs <- vapply(assets, `[[`, character(1L), "ref")
    update("cash_import_asset", choice_vector(assets), keep(ref_for("assets", cash_import_remembered$asset), asset_refs, if (length(assets) == 1L) assets[[1L]]$ref else ""))
    adapters <- tryCatch(cash_statement_service$adapters(), error = function(error) NULL)
    adapters <- import_offered_filter_list(adapters)   # nur Plugins, die in mindestens einem Portfolio aktiv sind (rc.381)
    cash_import_adapter_list(adapters)
    if (length(adapters)) {
      adapter_ids <- vapply(adapters, `[[`, character(1L), "adapter_id")
      update("cash_import_adapter", stats::setNames(adapter_ids, vapply(adapters, `[[`, character(1L), "label")), keep(input$cash_import_adapter, adapter_ids, adapter_ids[[1L]]))
    }
    invisible(model)
  }
  shiny::observeEvent(cash_catalog(), cash_import_populate(cash_catalog()), ignoreNULL = TRUE)
  # Der Pruefstand des Formats kommt aus dem Manifest des Lesers (offered(), #486); vor dem ersten Oeffnen des Imports steht "noch nicht geprueft".
  import_offered_reader <- function(reader_id, domain) {
    offered <- import_offered(); if (is.null(offered)) return(NULL)
    hit <- Filter(function(item) identical(item$reader_id, reader_id) && identical(item$domain, domain), offered$readers)
    if (length(hit)) hit[[1L]] else NULL
  }
  output$statement_exchange_reader_info <- shiny::renderUI(data_reward_reader_info_v1(input$statement_exchange_adapter,
                                                                                    import_offered_reader(input$statement_exchange_adapter, "reward")))
  output$cash_import_formats <- shiny::renderUI(data_cash_statement_formats_ui_v1(cash_import_adapter_list(), input$cash_import_adapter))
  cash_import_load <- function() {
    model <- tryCatch({refresh_cash_catalog(); cash_catalog()}, error = function(error) NULL)
    if (is.null(model)) {
      cash_import_message(list(tone = "warning", title = "Noch kein Cash-Asset", copy = "Bitte zuerst im Tab Stammdaten ein Asset der Art „Cash“ (z. B. EUR) und ein Konto für das Cash-Guthaben anlegen."))
      return(invisible(NULL))
    }
    cash_import_populate(model); cash_import_message(NULL)
    invisible(model)
  }
  cash_import_scope <- function() {
    selection <- tryCatch(.data_cash_coverage_selection(cash_editor, runtime$context), error = function(error) NULL)
    if (is.null(selection)) return(NULL)
    account <- tryCatch(.data_cash_coverage_resolve(selection, "accounts", input$cash_import_account), error = function(error) NULL)
    asset <- tryCatch(.data_cash_coverage_resolve(selection, "assets", input$cash_import_asset), error = function(error) NULL)
    if (is.null(account) || is.null(asset)) return(NULL)
    list(portfolio_id = account$portfolio_id, account_id = account$account_id, cash_asset_id = asset$asset_id)
  }
  # Dateien aus der Ablage (#434) gelten, bis neue Dateien gewaehlt werden oder der Import neu beginnt.
  cash_import_archive <- shiny::reactiveVal(NULL)
  cash_import_upload <- function() {
    archive <- cash_import_archive(); if (!is.null(archive)) return(archive)
    upload <- input$cash_import_file
    if (is.null(upload) || identical(paste(upload$datapath, collapse = "\n"), cash_import_cleared_upload())) NULL else upload
  }
  shiny::observeEvent(input$cash_import_file, cash_import_archive(NULL), priority = 10L)
  cash_import_reset <- function() { cash_import_preview(NULL); cash_import_result(NULL); cash_import_confirmed(NULL) }
  shiny::observeEvent(list(input$cash_import_adapter, input$cash_import_account, input$cash_import_asset, input$cash_import_file), cash_import_reset(), ignoreInit = TRUE)
  shiny::observeEvent(input$cash_import_load_run, cash_import_load())
  # Load at session start and whenever the transaction tab is opened, so Cash assets or
  # accounts created meanwhile in the master data tab appear without an extra click.
  # Einmal je Sitzung, nicht bei jedem Betreten: Jeder Schreibvorgang, der den
  # Cash-Stand oder den Katalog aendert, liest ihn danach selbst neu. Bei jedem
  # Wechsel in den Reiter erneut zu lesen kostete jedes Mal mehrere Sekunden.
  #
  # Ohne ignoreInit: Der Transaktionsreiter ist beim Start schon offen, und der
  # Startzustand zaehlt fuer ignoreInit nicht als Wechsel. rc.228 hatte es gesetzt,
  # um das Lesen vom Start wegzuschieben - und damit blieb die Cash-Karte leer,
  # bis man den Reiter verliess und zurueckkam (im Browser gefunden 09.10.2026;
  # der Vertragstest ohne Browser setzt den Reiter nachtraeglich und sah es nicht).
  shiny::observeEvent(input$asset_center_step, {
    if (identical(input$asset_center_step, "transactions") && is.null(cash_catalog())) cash_import_load()
  })
  cash_import_run_preview <- function() {
    upload <- cash_import_upload(); scope <- cash_import_scope()
    if (is.null(scope)) { cash_import_message(list(tone = "warning", title = "Konto und Cash-Asset wählen", copy = "Bitte das Cash-Konto und das Cash-Asset (Währung) auswählen.")); return() }
    if (is.null(upload)) { cash_import_message(list(tone = "warning", title = "Keine Datei gewählt", copy = "Bitte den Kontoauszug auswählen.")); return() }
    tryCatch({
      preview <- shiny::withProgress(message = "Auszug wird geprüft", value = 0.3, cash_statement_service$preview(input$cash_import_adapter, as.list(upload$datapath), as.list(upload$name), scope$account_id, cash_import_confirmed()))
      cash_import_preview(preview); cash_import_result(NULL); cash_import_message(NULL)
      # Nennt der Auszug Zinsen brutto, die netto gebucht sind? Nur lesend; korrigiert
      # wird erst nach eigener Bestaetigung.
      cash_import_gross(tryCatch(cash_statement_service$gross_preview(
        input$cash_import_adapter, as.list(upload$datapath), as.list(upload$name), scope$account_id, cash_import_confirmed(), input$cash_import_gross_from),
        error = function(error) NULL))
    }, error = function(error) cash_import_message(
      if (grepl("cash_statement_balance_confirmation_invalid", conditionMessage(error), fixed = TRUE)) {
        cash_import_confirmed(NULL)
        list(tone = "error", title = "Saldobestätigung nicht möglich",
             copy = "Der Stichtag darf nicht vor der jüngsten Bewegung der Auszüge liegen, und der Saldo muss ein Betrag sein (z. B. 1.234,56). Es wurde nichts gebucht.")
      } else
      if (grepl("cash_statement_multiple_accounts", conditionMessage(error), fixed = TRUE))
        list(tone = "error", title = "Datei mit mehreren Konten",
             copy = "Der Export nennt mehrere Konten (Spalte „Kontoname“). Bitte je Konto exportieren – bei C24 oben das Konto wählen statt „Alle Konten“. Es wurde nichts gebucht.")
      else
      if (!is.null(reader_message <- data_cash_statement_reader_message_v1(conditionMessage(error), cash_statement_reader_label(input$cash_import_adapter))))
        reader_message
      else
      if (grepl("cash_statement_pdf_tool_missing", conditionMessage(error), fixed = TRUE))
        list(tone = "error", title = "PDF-Werkzeug fehlt",
             copy = "Für PDF-Auszüge wird das Programm „pdftotext“ (Paket poppler-utils) benötigt. Alternativ den Auszug als Textdatei speichern; es wurde nichts gebucht.")
      else {
        # Welche Quelle liest diese Datei? Ein Vorschlag statt einer Sackgasse.
        matches <- tryCatch(cash_statement_service$detect(as.list(upload$datapath), as.list(upload$name)), error = function(inner) NULL)
        labels <- if (length(matches)) vapply(matches, function(item) as.character(item$label), character(1L)) else character()
        list(tone = "error", title = "Auszug nicht lesbar",
             copy = if (length(labels)) sprintf("Die Datei passt nicht zur gewählten Quelle. Sie passt zu: %s. Bitte diese Quelle wählen; es wurde nichts gebucht.", paste(labels, collapse = " oder "))
                    else "Die Datei passt zu keiner bekannten Quelle oder ist beschädigt. Bitte Quelle und Datei prüfen; es wurde nichts gebucht.")
      }))
  }
  shiny::observeEvent(input$cash_import_preview_run, cash_import_run_preview())
  # Saldo bestaetigen: Stichtag und Betrag, dann dieselbe Pruefung mit diesem zweiten Beleg.
  shiny::observeEvent(input$cash_import_balance_run, {
    raw <- trimws(as.character(input$cash_import_balance_value))
    normalized <- if (grepl(",", raw, fixed = TRUE)) gsub(",", ".", gsub(".", "", raw, fixed = TRUE), fixed = TRUE) else raw
    normalized <- gsub("[ €]", "", normalized)
    day <- tryCatch(as.Date(input$cash_import_balance_date), error = function(error) NA)
    if (!grepl("^-?[0-9]+(\\.[0-9]{1,2})?$", normalized) || is.na(day)) {
      cash_import_message(list(tone = "warning", title = "Saldo prüfen", copy = "Bitte Stichtag und Saldo angeben, z. B. 1.234,56.")); return()
    }
    cash_import_confirmed(list(as_of_date = format(day, "%Y-%m-%d"), balance_decimal = normalized))
    cash_import_run_preview()
  })
  shiny::observeEvent(input$cash_import_balance_clear, { cash_import_confirmed(NULL); cash_import_run_preview() })
  shiny::observeEvent(input$cash_import_book_run, {
    preview <- cash_import_preview(); upload <- cash_import_upload(); scope <- cash_import_scope()
    if (is.null(preview) || is.null(upload) || is.null(scope) || preview$coverage$proposal %in% c("blocked", "gap")) return()
    # Guard against stale choices: the account and the Cash asset must still be active.
    active <- tryCatch({refresh_cash_catalog(); selection <- .data_cash_coverage_selection(cash_editor, runtime$context)
      !is.null(selection$accounts$ref_by_id[[scope$account_id]]) && !is.null(selection$assets$ref_by_id[[scope$cash_asset_id]])}, error = function(error) FALSE)
    if (!isTRUE(active)) {
      cash_import_reset()
      cash_import_message(list(tone = "error", title = "Cash-Konto oder Cash-Asset nicht aktiv",
        copy = "Das gewählte Konto oder Cash-Asset ist nicht (mehr) aktiv, z. B. archiviert. Es wurde nichts gebucht. Bitte im Tab Stammdaten ein aktives Cash-Asset anlegen und hier neu wählen."))
      return()
    }
    # Pruefstand (rc.380): Ohne Haekchen nichts buchen, solange ein Leser noch nicht an Ihren Belegen geprueft ist; die Vorschau bleibt stehen.
    if (data_statement_reader_check_required_v1(preview$reader_check) && !isTRUE(input$cash_import_reader_ack)) {
      shiny::showNotification("Bitte erst die Vorschau mit dem Auszug vergleichen und das Häkchen setzen. Es wurde nichts gebucht.", type = "warning", duration = 8)
      return()
    }
    tryCatch({
      total <- NULL; done <- 0L; last <- NULL; provenance_failed <- NULL; reader_check <- NULL
      shiny::withProgress(message = "Cash-Bewegungen werden gebucht", value = 0, {
        repeat {
          chunk <- cash_statement_service$apply(input$cash_import_adapter, as.list(upload$datapath), as.list(upload$name), scope, input$cash_import_text, 1000L, now_utc(), cash_import_confirmed(),
                                                reader_check_acknowledged = isTRUE(input$cash_import_reader_ack))
          if (!is.null(chunk$reader_check_recorded)) reader_check <- as.character(chunk$reader_check_recorded)
          if (is.null(total)) total <- max(1L, as.integer(chunk$total_command_count))
          done <- total - as.integer(chunk$remaining_command_count); last <- chunk
          if (is.character(chunk$provenance_status) && startsWith(chunk$provenance_status, "failed")) provenance_failed <- chunk$provenance_status
          shiny::setProgress(done / total, detail = paste(done, "von", total, "Schritten"))
          if (!identical(chunk$status, "in_progress")) break
        }
      })
      cash_import_result(list(new = preview$counts$new, booked = preview$counts$booked, corrected = if (is.null(preview$corrections$count)) 0L else preview$corrections$count, coverage = preview$coverage,
                              provenance = provenance_failed, reader_check = reader_check))
      cash_import_preview(NULL)
      cash_movements_model(tryCatch(cash_statement_service$movements(scope$account_id), error = function(error) NULL))
      shiny::updateSelectInput(session, "cash_movements_account", selected = input$cash_import_account)
      invisible(tryCatch(refresh_cash_catalog(), error = function(error) NULL))
    }, error = function(error) {
      code <- if (is.null(error$code)) "" else as.character(error$code)
      # Name the real reason; a stale selection (archived asset or account) is the common case.
      if (grepl("catalog", code, fixed = TRUE) || identical(code, "cash_statement_input_invalid")) {
        invisible(tryCatch(cash_import_load(), error = function(inner) NULL)); cash_import_reset()
        cash_import_message(list(tone = "error", title = "Cash-Konto oder Cash-Asset nicht aktiv",
          copy = "Das gewählte Konto oder Cash-Asset ist nicht (mehr) aktiv, z. B. archiviert. Es wurde nichts gebucht. Bitte im Tab Stammdaten ein aktives Cash-Asset anlegen und hier neu wählen."))
      } else if (identical(code, "cash_statement_coverage_conflict")) {
        cash_import_message(list(tone = "error", title = "Abdeckung passt nicht", copy = data_cash_statement_coverage_text_v1(list(proposal = "blocked"))))
      } else if (startsWith(code, "statement_reader_")) {
        reader <- data_statement_reader_message_v1(code, input$cash_import_adapter, "Es wurde nichts gebucht.")
        cash_import_message(list(tone = "error", title = reader$title, copy = reader$copy))
      } else {
        cash_import_message(list(tone = "error", title = "Buchung unterbrochen",
          copy = "Nicht alle Bewegungen wurden gebucht. Erneut „buchen“ setzt fort; bereits gebuchte Schritte werden erkannt und nicht doppelt geschrieben."))
      }
    })
  })
  shiny::observeEvent(input$cash_import_restart, {
    upload <- input$cash_import_file; cash_import_cleared_upload(if (is.null(upload)) NULL else paste(upload$datapath, collapse = "\n")); cash_import_archive(NULL)
    cash_import_reset(); cash_import_message(NULL)
  })
  data_statement_archive_source_server_v1(input, output, session, "cash_import", statement_archive_service,
    on_take = function(frame) { cash_import_archive(frame); cash_import_reset(); cash_import_message(NULL) },
    account_ids = function() { scope <- cash_import_scope(); if (is.null(scope)) character() else scope$account_id },
    kinds = c("account_statement", "transaction_export"))
  shiny::observeEvent(input$cash_movements_account, {
    selection <- tryCatch(.data_cash_coverage_selection(cash_editor, runtime$context), error = function(error) NULL); if (is.null(selection)) return()
    account <- if (nzchar(input$cash_movements_account)) tryCatch(.data_cash_coverage_resolve(selection, "accounts", input$cash_movements_account), error = function(error) NULL) else NULL
    cash_movements_model(tryCatch(cash_statement_service$movements(if (is.null(account)) NULL else account$account_id), error = function(error) NULL))
  }, ignoreInit = TRUE)
  output$cash_import_state <- shiny::renderUI({
    message <- cash_import_message(); preview <- cash_import_preview(); result <- cash_import_result()
    if (!is.null(message)) return(portelyra_status_panel(message$title, message$copy, tone = message$tone))
    if (!is.null(result)) {
      # Bewegungsloser Auszug (#440): Festgehalten wird nur der Saldo; das sagt die Meldung statt "0 neue Bewegungen".
      if (identical(result$coverage$reason, "balance_anchor") && as.integer(result$new) == 0L)
        return(portelyra_status_panel("Saldo abgeglichen", sprintf("Keine Bewegung gebucht; der Saldo %s am %s ist als Abgleich festgehalten.",
          result$coverage$reconcile_to$observed_balance_decimal, format(as.Date(result$coverage$reconcile_to$as_of_date), "%d.%m.%Y")), tone = "positive"))
      corrected <- if (is.null(result$corrected)) 0L else as.integer(result$corrected)
      return(portelyra_status_panel("Cash-Auszug gebucht", paste(sprintf("%d neue Bewegungen gebucht · %d waren bereits vorhanden%s.", as.integer(result$new), as.integer(result$booked),
        if (corrected > 0L) sprintf(" · %d Tag(e) korrigiert", corrected) else ""), data_cash_statement_coverage_text_v1(result$coverage),
        data_statement_provenance_note_v1(result$provenance), data_statement_reader_check_note_v1(result$reader_check)), tone = "positive"))
    }
    if (!is.null(preview)) {
      counts <- preview$counts
      reversals <- if (is.null(preview$interest_reversals)) 0L else as.integer(preview$interest_reversals)
      copy <- paste(sprintf("%d neu (davon %d Zinsen) · %d bereits gebucht · %d nicht lesbare Zeilen.", as.integer(counts$new), as.integer(counts$interest_new), as.integer(counts$booked), as.integer(counts$diagnostics)),
        if (reversals > 0L) sprintf("%d stornierte Zinsbuchungen wurden verrechnet: sie bleiben als Ein- und Auszahlung stehen, zählen aber nicht als Ertrag.", reversals) else "",
        data_cash_statement_coverage_text_v1(preview$coverage), data_cash_statement_further_gaps_text_v1(preview$chain_gaps),
        data_cash_statement_corrections_text_v1(preview$corrections),
        data_cash_statement_held_back_text_v1(preview$held_back), data_cash_statement_skipped_text_v1(preview$files),
        data_cash_statement_reader_note_v1(preview$reader))
      fixes <- if (is.null(preview$corrections$count)) 0L else as.integer(preview$corrections$count)
      # Gesperrter Stapel (#522, gesehen 05.11.2026): Die Ueberschrift sagt „nicht buchbar“, nicht „bereit zum Buchen“ - darunter steht
      # ohnehin „es wurde nichts gebucht“, und der Knopf fehlt.
      return(shiny::tagList(portelyra_status_panel(if (preview$coverage$proposal %in% c("blocked", "gap")) sprintf("Nicht buchbar – %d Bewegungen geprüft", as.integer(counts$new) + as.integer(counts$booked))
          else if (as.integer(counts$new) > 0L || fixes > 0L) paste(c(if (as.integer(counts$new) > 0L) sprintf("%d Bewegungen bereit zum Buchen", as.integer(counts$new)),
          if (fixes > 0L) sprintf("%d Korrektur(en)", fixes)), collapse = ", ") else "Nichts Neues zu buchen", copy,
        tone = if (preview$coverage$proposal %in% c("blocked", "gap")) "error" else if (as.integer(counts$new) > 0L || fixes > 0L) "warning" else "positive"),
        data_statement_reader_check_panel_v1(preview$reader_check)))
    }
    if (is.null(cash_catalog())) return(portelyra_status_panel("Cash-Konten werden geladen", "Falls die Auswahl leer bleibt: „Cash-Konten laden“.", tone = "neutral"))
    portelyra_status_panel("Auszug wählen", "Quelle, Cash-Konto, Währung und Datei wählen, dann „Auszug prüfen“. Die Prüfung schreibt nichts.", tone = "neutral")
  })
  output$cash_import_action <- shiny::renderUI({
    preview <- cash_import_preview(); result <- cash_import_result()
    restart <- shiny::tags$button(type = "button", id = "cash_import_restart_button", class = "btn btn-default",
      onclick = "var f=document.getElementById('cash_import_file');if(f){f.value='';var g=f.closest('.form-group');if(g){var t=g.querySelector('input[type=text]');if(t){t.value='';}var bar=g.querySelector('.progress');if(bar){bar.style.visibility='hidden';}}}Shiny.setInputValue('cash_import_restart',Date.now(),{priority:'event'});return false;",
      "Neuen Auszug beginnen")
    if (!is.null(result)) return(restart)
    if (is.null(cash_catalog())) return(shiny::actionButton("cash_import_load_run", "Cash-Konten laden", class = "btn-primary"))
    if (is.null(preview)) return(shiny::div(class = "pl-editor-actions", shiny::actionButton("cash_import_preview_run", "Auszug prüfen", class = "btn-primary"),
      shiny::actionButton("cash_import_load_run", "Cash-Konten neu laden", class = "btn-default")))
    new <- as.integer(preview$counts$new)
    fixes <- if (is.null(preview$corrections$count)) 0L else as.integer(preview$corrections$count)
    # Saldo abgleichen ohne neue Bewegung: nach eigener Bestaetigung oder bei bewegungslosen Auszuegen (#440).
    reconcile_only <- new == 0L && fixes == 0L && !is.null(preview$coverage$reconcile_to) &&
      (isTRUE(preview$coverage$owner_confirmed) || identical(preview$coverage$reason, "balance_anchor"))
    if ((new > 0L || fixes > 0L || reconcile_only) && !preview$coverage$proposal %in% c("blocked", "gap"))
      return(shiny::div(class = "pl-editor-actions", data_statement_reader_check_ack_v1("cash_import_reader_ack", preview$reader_check, "dem Auszug"),
        shiny::actionButton("cash_import_book_run", if (reconcile_only) "Saldo abgleichen" else
          paste(c(if (new > 0L) sprintf("%d Bewegungen buchen", new), if (fixes > 0L) sprintf("%d korrigieren", fixes)), collapse = ", "), class = "btn-primary"),
        shiny::span(class = "pl-field-hint", "Bucht genau diese Bewegungen und die Abdeckung. Rückgängig nur über die Cash-Korrektur."), restart))
    restart
  })
  output$cash_import_balance_ui <- shiny::renderUI({
    preview <- cash_import_preview(); confirmed <- cash_import_confirmed()
    # Schon ohne Saldo als "teilweise erfasst" gebucht und nichts Neues: Hier weist der Kern die Bestaetigung ab (#522, 31.10.2026).
    # Statt eines Feldes, das erst nach dem Ausfuellen scheitert, der Weg dorthin, wo es geht.
    if (!is.null(preview) && is.null(cash_import_result()) && is.null(confirmed) && isTRUE(preview$balance_confirmation_elsewhere))
      return(shiny::div(class = "pl-editor-actions",
        shiny::span(class = "pl-field-hint", "Dieses Konto ist schon als „teilweise erfasst“ gebucht. Den Saldo bestätigen Sie unter „Manuell“ → „Cash“ → „Saldo prüfen · Abdeckung abstimmen“ (Stichtag, Saldo, Nachweis); das hebt das Konto auf „abgestimmt“."),
        shiny::tags$button(type = "button", class = "btn btn-default", id = "cash_import_balance_elsewhere_button",
          onclick = "Shiny.setInputValue('cash_import_balance_elsewhere',Date.now(),{priority:'event'});setTimeout(function(){var h=document.getElementById('cash_check_heading');if(h){h.scrollIntoView({behavior:'smooth',block:'start'});}},700);return false;",
          "Zu „Saldo prüfen“")))
    if (is.null(preview) || !is.null(cash_import_result()) || !isTRUE(preview$balance_confirmation_possible)) return(NULL)
    if (!is.null(confirmed))
      return(shiny::div(class = "pl-editor-actions",
        shiny::span(class = "pl-field-hint", sprintf("Bestätigter Saldo: %s am %s.", confirmed$balance_decimal, format(as.Date(confirmed$as_of_date), "%d.%m.%Y"))),
        shiny::actionButton("cash_import_balance_clear", "Bestätigung entfernen", class = "btn-default")))
    latest <- if (is.null(preview$latest_movement_date)) Sys.Date() else as.Date(preview$latest_movement_date)
    shiny::tags$details(class = "pl-disclosure", open = NA,
      shiny::tags$summary("Saldo bestätigen (Konto bis zum Stichtag vollständig abgleichen)"),
      shiny::div(class = "pl-form-grid",
        shiny::dateInput("cash_import_balance_date", "Stichtag", value = max(Sys.Date(), latest), min = latest, format = "dd.mm.yyyy", language = "de"),
        shiny::textInput("cash_import_balance_value", "Saldo am Stichtag (€)", placeholder = "z. B. 1.234,56")),
      shiny::span(class = "pl-field-hint", sprintf("Den Saldo aus der Banking-App oder dem Konto übernehmen. Der Stichtag darf nicht vor der jüngsten Bewegung (%s) liegen.", format(latest, "%d.%m.%Y"))),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("cash_import_balance_run", "Saldo bestätigen und prüfen", class = "btn-primary")))
  })
  shiny::observeEvent(input$cash_import_balance_elsewhere, {
    account <- input$cash_import_account
    shiny::updateTabsetPanel(session, "transactions_view", selected = "manual")
    shiny::updateRadioButtons(session, "transactions_mode", selected = "cash")
    if (is.character(account) && length(account) == 1L && nzchar(account)) shiny::updateSelectInput(session, "cash_check_account", selected = account)
  })
  output$cash_import_gross_ui <- shiny::renderUI({
    correction <- cash_import_gross()
    if (is.null(cash_import_preview()) || !is.null(cash_import_result()) || !is.list(correction)) return(NULL)
    count <- as.integer(correction$correction_count)
    hidden <- if (is.null(correction$out_of_window_count)) 0L else as.integer(correction$out_of_window_count)
    hidden_note <- if (hidden && !is.null(correction$consider_from)) sprintf("%d weitere Brutto-Vorschläge vor dem %s nicht betrachtet.", hidden,
      format(as.Date(correction$consider_from), "%d.%m.%Y")) else NULL
    if (is.na(count) || count == 0L) return(if (is.null(hidden_note)) NULL else shiny::p(class = "pl-section-copy", hidden_note))
    shiny::tags$details(class = "pl-disclosure", open = NA,
      shiny::tags$summary(sprintf("%d Zinserträge sind netto gebucht · auf brutto heben", count)),
      shiny::p(class = "pl-section-copy", sprintf(paste(
        "Dieser Auszug nennt den Bruttozins; gebucht wurde damals der Betrag nach einbehaltener Steuer.",
        "Dadurch fehlen %s € im allgemeinen Topf. Die Korrektur hebt nur den Ertrag;",
        "der Geldfluss bleibt unberührt, denn auf dem Konto landete der Nettobetrag."), correction$withheld_tax_total_decimal), if (!is.null(hidden_note)) paste("", hidden_note)),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("cash_import_gross_table")),
      shiny::div(class = "pl-editor-actions",
        shiny::checkboxInput("cash_import_gross_confirm", "Genau diese Korrekturen bestätigen", FALSE),
        shiny::actionButton("cash_import_gross_run", sprintf("%d Erträge auf brutto heben", count), class = "btn-primary")))
  })
  output$cash_import_gross_table <- shiny::renderTable(data_cash_statement_gross_frame_v1(cash_import_gross()), bordered = TRUE, striped = TRUE, spacing = "xs")
  shiny::observeEvent(input$cash_import_gross_run, {
    correction <- cash_import_gross(); upload <- cash_import_upload(); scope <- cash_import_scope()
    if (is.null(correction) || is.null(upload) || is.null(scope)) return()
    if (!isTRUE(input$cash_import_gross_confirm)) {
      cash_import_message(list(tone = "warning", title = "Bestätigung fehlt",
        copy = "Bitte die Korrekturen ausdrücklich bestätigen. Es wurde nichts geändert."))
      return()
    }
    tryCatch({
      result <- shiny::withProgress(message = "Zinserträge werden auf brutto gehoben", value = 0.4,
        cash_statement_service$gross_apply(input$cash_import_adapter, as.list(upload$datapath), as.list(upload$name),
                                           scope, as.integer(correction$correction_count), now_utc(), cash_import_confirmed(),
                                           if (is.null(correction$consider_from)) "" else correction$consider_from))
      shiny::updateCheckboxInput(session, "cash_import_gross_confirm", value = FALSE)
      cash_import_message(list(tone = "success", title = sprintf("%s Erträge auf brutto gehoben", result$corrected_income_count),
        copy = sprintf("Die einbehaltene Steuer von %s € steht jetzt im allgemeinen Topf. Vorgänger bleiben erhalten; der Geldfluss ist unverändert.",
                       result$withheld_tax_total_decimal)))
      cash_import_run_preview()
    }, error = function(error) cash_import_message(list(tone = "error", title = "Korrektur nicht ausgeführt",
      copy = paste("Die Cash-Autorität hat die Korrektur abgewiesen:", conditionMessage(error), "Es wurde nichts geändert."))))
  })
  output$cash_import_files <- shiny::renderTable(data_cash_statement_files_frame_v1(cash_import_preview()), bordered = TRUE, striped = TRUE, spacing = "xs")
  output$cash_import_rows <- shiny::renderTable(data_cash_statement_rows_frame_v1(cash_import_preview()), bordered = TRUE, striped = TRUE, spacing = "xs")
  cash_account_label_for <- function(account_id) {
    selection <- tryCatch(.data_cash_coverage_selection(cash_editor, runtime$context), error = function(error) NULL); if (is.null(selection)) return("")
    ref <- selection$accounts$ref_by_id[[account_id]]; if (is.null(ref)) return("")
    row <- selection$accounts$by_ref[[ref]]; data_cash_account_label_v1(row$label, row$account_type)
  }
  output$cash_movements_summary <- shiny::renderUI({
    model <- cash_movements_model(); if (is.null(model)) return(NULL)
    modes <- c(income_only = "nur Zinsen", partial = "teilweise", complete_reconciled = "vollständig abgeglichen", not_tracked = "nicht erfasst")
    coverage <- if (length(model$coverage_modes)) paste(unname(modes[unlist(model$coverage_modes)]), collapse = ", ") else "noch keine"
    portelyra_status_panel(sprintf("Saldo %s · Zinsen gesamt %s (%d Buchungen)", if (is.null(model$balance_decimal)) "unbekannt" else model$balance_decimal, model$interest_total_decimal, as.integer(model$interest_count)),
      paste0("Abdeckung: ", coverage, if (is.list(model$last_reconciliation)) sprintf(" · letzter Abgleich %s: %s", format(as.Date(model$last_reconciliation$as_of_date), "%d.%m.%Y"), model$last_reconciliation$observed_balance_decimal) else "",
        if (as.integer(model$movement_count) > DATA_CASH_TABLE_LIMIT) sprintf(" · Tabelle zeigt die jüngsten %d von %d Bewegungen", DATA_CASH_TABLE_LIMIT, as.integer(model$movement_count)) else ""), tone = "neutral")
  })
  output$cash_movements_table <- shiny::renderTable(data_cash_movements_frame_v1(cash_movements_model(), cash_account_label_for), bordered = TRUE, striped = TRUE, spacing = "xs")
  refresh_cash_catalog <- function() {
    view<-data_cash_coverage_editor_read_view_v1(cash_editor,runtime$context);cash_read_view(view)
    model<-data_cash_coverage_editor_refresh_v1(cash_editor,runtime$context);cash_catalog(model)
    shiny::updateSelectInput(session,"cash_portfolio",choices=choice_vector(model$portfolios))
    shiny::updateSelectInput(session,"cash_account",choices=choice_vector(model$accounts))
    # Die einfachen Formulare behalten ihr Konto ueber eine Auffrischung hinweg -
    # nach jeder Buchung folgt meist die naechste auf demselben Konto.
    for(feld in c("cash_simple_account","cash_check_account")) {
      bisher<-shiny::isolate(input[[feld]]);refs<-vapply(model$accounts,`[[`,character(1L),"ref")
      shiny::updateSelectInput(session,feld,choices=choice_vector(model$accounts),selected=if(is.character(bisher)&&length(bisher)==1L&&bisher%in%refs)bisher else "")
    }
    shiny::updateSelectInput(session,"cash_related_account",choices=choice_vector(model$accounts))
    shiny::updateSelectInput(session,"cash_asset",choices=choice_vector(model$cash_assets))
    revision_choices<-if(!length(model$revision_candidates))c("Keine aktiven Cash-Datensätze"="")else stats::setNames(
      vapply(model$revision_candidates,`[[`,character(1L),"record_ref"),
      vapply(model$revision_candidates,function(row)paste(row$effective_date,"·",row$fact_kind,"·",row$account_label,"·",row$cash_asset_label),character(1L)))
    shiny::updateSelectizeInput(session,"cash_predecessors",choices=revision_choices,selected=character(),server=TRUE)
    recovery_choices<-if(!length(model$recovery_candidates))c("Keine Kandidaten für die Wiederaufnahme"="")else stats::setNames(
      vapply(model$recovery_candidates,`[[`,character(1L),"recovery_ref"),
      vapply(model$recovery_candidates,function(row)paste(row$operation_type,"·",row$recovery_reason,"·",row$attempted_at_utc),character(1L)))
    shiny::updateSelectInput(session,"cash_recovery_candidate",choices=recovery_choices,selected="");model
  }
  # Die Auswahl "verknuepftes Cash-Ereignis" fuehrt jede gebuchte Bewegung, oft
  # sehr viele Eintraege. Sie wurde bei jedem Lesen des Cash-Stands
  # neu aufgebaut und in den Browser geschickt, auch beim Sitzungsstart, obwohl
  # sie nur im zugeklappten Bereich "Erweitert" gebraucht wird. Jetzt entsteht sie, solange der Bereich offen ist: beim Oeffnen
  # und nach jedem Lesen des Cash-Stands.
  shiny::observe({
    if (!isTRUE(input$cash_advanced_open)) return()
    view <- cash_read_view()
    event_choices<-if(is.null(view)||!identical(view$status,"available")||!length(view$cash_history))c("Nicht verknüpfen"="")else c("Nicht verknüpfen"="",stats::setNames(
      vapply(view$cash_history,`[[`,character(1L),"cash_event_ref"),
      vapply(view$cash_history,function(row)paste(row$local_date,"·",row$event_type,"·",row$account_label,"·",row$amount_decimal,row$currency),character(1L))))
    shiny::updateSelectInput(session,"cash_linked_event",choices=event_choices,selected="")
  })
  cash_form <- function() list(
    action_type=input$cash_action,portfolio_ref=input$cash_portfolio,account_ref=input$cash_account,
    cash_asset_ref=input$cash_asset,related_account_ref=input$cash_related_account,
    coverage_mode=input$cash_coverage_mode,effective_from=optional_date(input$cash_effective_from),
    effective_to=optional_date(input$cash_effective_to),event_type=input$cash_event_type,
    local_date=optional_date(input$cash_local_date),local_time=input$cash_local_time,time_zone=input$cash_time_zone,
    effective_at_utc=input$cash_effective_utc,amount_decimal=input$cash_amount,flow_classification=input$cash_flow_classification,
    gross_income_decimal=input$cash_interest_amount,linked_cash_event_ref=input$cash_linked_event,
    as_of_date=optional_date(input$cash_as_of_date),observed_balance_decimal=input$cash_observed_balance,
    evidence_fingerprint=input$cash_evidence_fingerprint,
    revision_predecessor_refs=if(is.null(input$cash_predecessors))character()else input$cash_predecessors
  )
  refresh_catalog_model <- function() {
    model <- desktop_catalog_editor_refresh_v1(catalog_editor, runtime$context); catalog_model(model)
    catalog_csv_model(spotcore::desktop_csv_import_catalog_v1(runtime$context))
    invisible(model)
  }
  # Die Liste der Asset-Suche: alle sichtbaren Assets, eingegrenzt durch den
  # Asset-Filter. Die Bezeichnungen entstehen ueber die ganze Liste, damit ein
  # Asset mit und ohne Filter gleich heisst.
  asset_center_send_choices <- function(core, selected) {
    shown_assets <- Filter(function(row) !identical(row$status, "archived"), core$assets)
    filter_state <- list(status = "off")
    choices <- if (!length(shown_assets)) {
      c("Noch keine Assets" = "")
    } else {
      # Mit ISIN, wo es eine gibt (#448): Die Suche trifft dann auch per ISIN.
      labels <- vapply(shown_assets, function(row) {
        isin <- if (is.character(row$isin) && length(row$isin) == 1L && !is.na(row$isin) && nzchar(row$isin)) row$isin else NULL
        paste(c(row$display_name, row$asset_type, row$price_currency, isin), collapse = " · ")
      }, character(1L))
      counts <- table(labels)
      visible <- vapply(seq_along(labels), function(index) {
        label <- labels[[index]]
        if (counts[[label]] == 1L) label else paste(label, "· Auswahl", sum(labels[seq_len(index)] == label), "von", counts[[label]])
      }, character(1L))
      refs <- vapply(shown_assets, `[[`, character(1L), "ref")
      filtered <- data_asset_center_filter_apply_v1(
        shown_assets, asset_center_filter, shiny::isolate(activity_catalog()), shiny::isolate(activity_read_view()),
        activity_ref_for_center,
        if (is.character(selected) && length(selected) == 1L && !is.na(selected)) selected else ""
      )
      filter_state <- filtered$state
      visible[filtered$pinned] <- paste(visible[filtered$pinned], "· außerhalb des Filters")
      listed <- filtered$keep | filtered$pinned
      if (any(listed)) stats::setNames(refs[listed], visible[listed]) else c("Kein Asset passt zum Filter" = "")
    }
    # Kein Asset vorauswaehlen (#422, rc.332, Festlegung 27.10.2026): Bis rc.331 stand beim Start das erste Asset der Liste in
    # der Suche, immer dasselbe. Neutral ist: nichts gewaehlt, bis der Eigentuemer waehlt. Faellt ein gewaehltes Asset aus der
    # Liste (archiviert), bleibt die Suche leer statt still auf ein anderes zu springen.
    if (is.null(selected) || !selected %in% unname(choices)) selected <- ""
    # The complete public catalog is already loaded. Synchronous option replacement
    # prevents an older server-side Selectize load from undoing the next queue item.
    #
    # Der Server kennt die Auswahl nur so, wie sie beim Verarbeiten dieses Aufrufs
    # eintraf. Schickte er sie bei jedem Durchlauf mit, stellte er eine Auswahl
    # zurueck, die im Browser inzwischen getroffen war: Wer waehrend eines laufenden
    # "Asset-Center aktualisieren" ein anderes Asset waehlte, landete wieder beim
    # alten - und dieser Ruecksprung verwarf spaeter einen fertigen
    # Bewertungsentwurf (Auswahl nach 10 ms, Ruecksetzung
    # nach 420 ms). Sind Liste und Auswahl unveraendert, gibt es dem Browser nichts
    # mitzuteilen.
    held <- shiny::isolate(input$asset_center_asset)
    unchanged <- identical(choices, asset_center_choices_sent) &&
      is.character(held) && length(held) == 1L && identical(unname(selected), held)
    asset_center_choices_sent <<- choices
    if (!unchanged) shiny::updateSelectizeInput(session, "asset_center_asset", choices = choices, selected = selected, server = FALSE)
    asset_center_filter_status(filter_state)
    selected
  }
  # Ein Asset von Server-Seite waehlen. Liegt es ausserhalb des Filters, kennt die
  # Liste im Browser es nicht - dann geht die Liste mit, in der es steht.
  asset_center_select <- function(ref) {
    core <- shiny::isolate(asset_center_catalog())
    outside <- is.character(ref) && length(ref) == 1L && !is.na(ref) && nzchar(ref) &&
      !is.null(core) && !ref %in% unname(asset_center_choices_sent)
    if (outside) invisible(asset_center_send_choices(core, ref))
    else shiny::updateSelectizeInput(session, "asset_center_asset", selected = ref)
  }
  # Typen und Konten, die die Filterleiste anbietet. `account_ids` sind die
  # internen Kennungen der gewaehlten Konten von vor einem Neulesen.
  asset_center_filter_sync_options <- function(account_ids = NULL) {
    core <- shiny::isolate(asset_center_catalog()); if (is.null(core)) return(invisible(NULL))
    # Ohne Buchungssicht laesst sich kein Konto zuordnen; die Liste kaeme leer und
    # gleich darauf noch einmal. Der Beobachter der Sicht holt es nach.
    if (is.null(shiny::isolate(activity_catalog()))) return(invisible(NULL))
    visible <- function(rows) Filter(function(row) !identical(row$status, "archived"), rows)
    options <- data_asset_center_filter_options_v1(visible(core$assets), visible(core$accounts), activity_ref_for_center)
    accounts <- asset_center_filter$account_refs
    if (!is.null(account_ids)) accounts <- names(Filter(function(row) isTRUE(row$account_id %in% account_ids),
      asset_center_catalog_editor$catalog$maps$account))
    accounts <- intersect(unname(options$accounts), accounts)
    types <- intersect(unname(options$asset_types), asset_center_filter$asset_types)
    moved <- !identical(sort(accounts), sort(asset_center_filter$account_refs)) || !identical(sort(types), sort(asset_center_filter$asset_types))
    if (identical(options, asset_center_filter_options_sent) && !moved) return(invisible(NULL))
    asset_center_filter_options_sent <<- options
    asset_center_filter$account_refs <<- accounts; asset_center_filter$asset_types <<- types
    shiny::updateSelectizeInput(session, "asset_center_filter_accounts", choices = options$accounts, selected = accounts, server = FALSE)
    shiny::updateSelectizeInput(session, "asset_center_filter_types", choices = options$asset_types, selected = types, server = FALSE)
    invisible(NULL)
  }
  asset_center_refresh <- function(selected = input$asset_center_asset) {
    on.exit(asset_center_selected_ref <<- if (is.character(selected) && length(selected) == 1L && !is.na(selected)) selected else "", add = TRUE)
    previous_mapping_id <- tryCatch(asset_center_provider_editor$state$mapping_map[[input$asset_center_mapping]]$mapping_id,error=function(e)NULL)
    previous_id <- tryCatch(desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", selected), error = function(e) NULL)
    # Die Konten des Asset-Filters ueber das Neulesen retten: Katalog-Refs sind
    # Positionen in der Liste und verschieben sich, wenn ein Konto hinzukommt.
    filter_account_ids <- unlist(lapply(asset_center_filter$account_refs, function(ref) tryCatch(
      desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "account", ref),
      error = function(e) NULL)), use.names = FALSE)
    core <- desktop_catalog_editor_refresh_v1(asset_center_catalog_editor, runtime$context)
    providers <- data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context)
    if (!identical(asset_center_catalog_editor$catalog$catalog_fingerprint, asset_center_provider_editor$state$catalog_fingerprint))
      stop("asset_center_catalog_changed", call. = FALSE)
    if (!is.null(previous_id)) {
      matched <- names(Filter(function(r) identical(r$asset_id, previous_id), asset_center_catalog_editor$catalog$maps$asset))
      selected <- if (length(matched) == 1L) matched[[1L]] else ""
    }
    asset_center_catalog(core); asset_center_provider_catalog(providers)
    # Archived master data stays in the audit trail but disappears from every selection list.
    visible <- function(rows) Filter(function(row) !identical(row$status, "archived"), rows)
    shown_assets <- visible(core$assets); shown_portfolios <- visible(core$portfolios); shown_accounts <- visible(core$accounts)
    asset_center_filter_sync_options(filter_account_ids)
    selected <- asset_center_send_choices(core, selected)
    portfolio_choices <- if (!length(shown_portfolios)) c("Keine Portfolios" = "") else stats::setNames(
      vapply(shown_portfolios, `[[`, character(1L), "ref"),
      vapply(shown_portfolios, function(row) paste(row$display_name, "·", row$base_currency), character(1L))
    )
    retained_center_portfolio <- if (is.character(input$asset_center_portfolio) &&
      length(input$asset_center_portfolio) == 1L && input$asset_center_portfolio %in% unname(portfolio_choices)) {
      input$asset_center_portfolio
    } else if (length(shown_portfolios) == 1L) shown_portfolios[[1L]]$ref else ""
    shiny::updateSelectInput(session, "asset_center_portfolio", choices = portfolio_choices, selected = retained_center_portfolio)
    # Auswahl zum Umbenennen in den Einstellungen (#547): dieselben Portfolios, vorbelegt mit dem der Kopfzeile.
    retained_target <- if (is.character(input$asset_center_portfolio_target) && length(input$asset_center_portfolio_target) == 1L &&
      input$asset_center_portfolio_target %in% unname(portfolio_choices) && nzchar(input$asset_center_portfolio_target)) input$asset_center_portfolio_target else retained_center_portfolio
    shiny::updateSelectInput(session, "asset_center_portfolio_target", choices = portfolio_choices, selected = retained_target)
    asset_center_selected_portfolio_ref <<- retained_center_portfolio
    inventory <- data_asset_center_market_inventory_v1(core, providers)
    market_choices <- if (!length(inventory$rows)) c("Keine providerfähigen Assets" = "") else stats::setNames(
      vapply(inventory$rows, `[[`, character(1L), "asset_ref"),
      vapply(inventory$rows, function(row) paste(row$asset_name, "·", row$status_label), character(1L))
    )
    shiny::updateSelectInput(session, "asset_center_market_asset", choices = market_choices,
                             selected = if (selected %in% unname(market_choices)) selected else unname(market_choices)[[1L]])
    account_choices <- if (!length(shown_accounts)) c("Noch kein Verwahrkonto" = "") else stats::setNames(
      vapply(shown_accounts, `[[`, character(1L), "ref"),
      vapply(shown_accounts, function(row) paste(row$display_name, "·", row$account_type), character(1L))
    )
    shiny::updateSelectInput(session, "asset_center_custody_account", choices = c("Nicht vorauswählen" = "", account_choices), selected = "")
    selected_mappings <- Filter(function(row) identical(row$asset_ref, selected), providers$mappings)
    mapping_choices <- data_market_mapping_choices_v1(selected_mappings)
    retained <- Filter(function(row) !is.null(previous_mapping_id) && identical(asset_center_provider_editor$state$mapping_map[[row$ref]]$mapping_id,previous_mapping_id),selected_mappings)
    daily <- Filter(function(row)identical(row$capability,'daily_history'),selected_mappings)
    chosen <- if(length(retained)==1L)retained[[1L]] else if(length(daily))daily[[1L]] else NULL
    shiny::updateSelectInput(session,'asset_center_mapping',choices=mapping_choices,selected=if(is.null(chosen))'' else chosen$ref)
    # Same-ref updates do not produce a Shiny selection event. Refresh the form
    # explicitly, and revoke evidence/previews tied to the old mapping revision.
    if(!is.null(chosen) && identical(selected,input$asset_center_asset)) {
      asset_center_reset_confirmations()
      asset_center_apply_provider_draft(data_market_defaults_v1(mapping=chosen))
      shiny::updateSelectInput(session,'asset_center_provider_action',selected='revise')
      asset_center_defaults_notice('Gespeicherte Zuordnung · Änderungen erfordern eine neue Prüfung.')
    }
    core
  }
  asset_center_core_form <- function() list(
    action = "create", entity_type = "asset", entity_ref = "", portfolio_ref = "",
    display_name = input$asset_center_name, base_currency = "EUR", account_type = "securities",
    institution_label = "", asset_type = if (identical(input$asset_center_domain, "cash")) "cash" else input$asset_center_type,
    price_currency = toupper(input$asset_center_currency), quantity_scale = input$asset_center_scale,
    valuation_method = if (identical(input$asset_center_domain, "cash")) "unit_value" else input$asset_center_valuation,
    isin = if (identical(input$asset_center_domain, "cash")) "" else toupper(input$asset_center_isin)
  )
  asset_center_edit_form <- function() {
    form <- asset_center_core_form()
    form$action <- "update"; form$entity_ref <- input$asset_center_asset
    form$display_name <- input$asset_center_edit_name; form$isin <- toupper(input$asset_center_edit_isin)
    # Nur eine leere ISIN nachgetragen, Name unveraendert: eigener Befehl, die Kursfreigabe bleibt gueltig.
    prior <- asset_center_selected()
    if (!is.null(prior) && identical(form$display_name, prior$display_name) && (is.null(prior$isin) || !nzchar(prior$isin)) && nzchar(form$isin))
      form$action <- "set_isin"
    form
  }
  asset_center_price_currency_form <- function() list(
    action = "revise_price_currency", entity_type = "asset", entity_ref = input$asset_center_asset,
    portfolio_ref = "", display_name = "", base_currency = "EUR", account_type = "securities",
    institution_label = "", asset_type = "other",
    price_currency = toupper(input$asset_center_price_currency_target), quantity_scale = "0",
    valuation_method = "transaction_only", isin = ""
  )
  asset_center_fund_type_form <- function() {
    prior <- asset_center_selected()
    list(action = "revise_asset_type", entity_type = "asset", entity_ref = input$asset_center_asset,
      portfolio_ref = "", display_name = "", base_currency = "EUR", account_type = "securities", institution_label = "",
      asset_type = if (!is.null(prior) && identical(prior$asset_type, "etf")) "fund" else "etf",
      price_currency = "EUR", quantity_scale = "0", valuation_method = "transaction_only", isin = "")
  }
  asset_center_provider_form <- function() {
    asset_center_require_market(!identical(input$asset_center_provider_action, "create"))
    list(
    action = input$asset_center_provider_action, mapping_ref = input$asset_center_mapping,
    asset_ref = input$asset_center_asset, capability = input$asset_center_provider_capability,
    provider_id = input$asset_center_provider_id, provider_symbol = input$asset_center_provider_symbol,
    exchange_code = input$asset_center_provider_exchange, mic_code = toupper(input$asset_center_provider_mic),
    provider_currency = toupper(input$asset_center_provider_currency), expert_only = isTRUE(input$asset_center_provider_expert)
    )
  }
  asset_center_refresh_tax <- function() {
    if (!isTRUE(asset_center_tax_service$initialized())) stop("tax_ui_not_initialized", call. = FALSE)
    model <- tax_ui_catalog_view_model_v1(asset_center_tax_service$catalog())
    asset_center_tax_catalog(model)
    portfolio_choices <- if (!length(model$portfolios)) c("Kein Portfolio" = "") else stats::setNames(
      vapply(model$portfolios, `[[`, character(1L), "ref"), vapply(model$portfolios, `[[`, character(1L), "label")
    )
    asset_choices <- if (!length(model$assets)) c("Kein Asset" = "") else stats::setNames(
      vapply(model$assets, `[[`, character(1L), "ref"), vapply(model$assets, `[[`, character(1L), "label")
    )
    selected_asset <- ""
    core <- asset_center_catalog(); selected <- if (is.null(core)) NULL else tryCatch(data_asset_center_selected_v1(core, input$asset_center_asset), error = function(error) NULL)
    if (!is.null(selected)) {
      matches <- Filter(function(row) identical(row$label, selected$display_name), model$assets)
      if (length(matches) == 1L) selected_asset <- matches[[1L]]$ref
    }
    shiny::updateSelectInput(session, "asset_center_tax_portfolio", choices = c("Bitte wählen" = "", portfolio_choices), selected = if (length(model$portfolios) == 1L) model$portfolios[[1L]]$ref else "")
    shiny::updateSelectInput(session, "asset_center_tax_asset", choices = c("Bitte wählen" = "", asset_choices), selected = selected_asset)
    asset_center_tax_state("not_configured")
    model
  }
  asset_center_tax_payload <- function() {
    model <- asset_center_tax_catalog()
    if (is.null(model)) stop("tax_ui_catalog_invalid", call. = FALSE)
    code <- input$asset_center_tax_classification
    definitions <- Filter(function(row) identical(row$classification_code, code), model$classification_definitions)
    if (length(definitions) != 1L) stop("tax_ui_classification_invalid", call. = FALSE)
    definition <- definitions[[1L]]
    list(
      portfolio_ref = input$asset_center_tax_portfolio,
      asset_ref = input$asset_center_tax_asset,
      classification_code = code,
      tax_bucket = definition$tax_bucket,
      partial_exemption_rate_decimal = input$asset_center_tax_partial,
      effective_from_year = as.integer(input$asset_center_tax_year),
      effective_to_year = NULL
    )
  }
  catalog_form <- function() list(
    action = "archive", entity_type = input$catalog_entity_type, entity_ref = input$catalog_entity_ref,
    portfolio_ref = "", display_name = "", base_currency = "EUR", account_type = "securities",
    institution_label = "", asset_type = "other", price_currency = "EUR", quantity_scale = "0",
    valuation_method = "transaction_only", isin = ""
  )
  refresh_run_catalog <- function() {
    model <- spotcore::desktop_run_center_catalog_v1(run_center, runtime$context); run_catalog(model)
    shiny::updateSelectInput(session, "run_portfolio", choices = choice_vector(model$portfolios)); model
  }
  load_published_workflow <- function() {
    published_workflow_loaded <<- TRUE
    published_workflow(tryCatch(
      desktop_workflow_display_state_v1(desktop_workflow_read_latest_v1(workflow_service)),
      spot_display_reader_error = function(error) desktop_workflow_display_state_v1(error_code = error$code),
      error = function(error) desktop_workflow_display_state_v1(error_code = "display_boundary_failed")
    ))
  }
  # Die Felder des gewaehlten Assets, so wie der Browser sie gerade hat.
  run_evidence_live <- function() lapply(DESKTOP_RUN_EVIDENCE_FIELDS, function(id) input[[id]])
  # Je aktivem Asset alle Felder: gespeichert oder Vorgabe; fuer das gewaehlte Asset gelten die Felder im Browser.
  run_asset_form <- function(asset) desktop_run_evidence_values_v1(run_evidence_store(), asset,
    if (identical(run_evidence_current(), asset$ref)) run_evidence_live() else NULL)
  run_evidence_assets <- function() {
    catalog <- run_catalog()
    if (is.null(catalog)) list() else Filter(function(asset) asset$asset_type != "cash" && asset$status == "active", catalog$assets)
  }
  run_evidence_show <- function(asset) {
    values <- desktop_run_evidence_values_v1(run_evidence_store(), asset)
    for (field in names(DESKTOP_RUN_EVIDENCE_FIELDS)) {
      id <- DESKTOP_RUN_EVIDENCE_FIELDS[[field]]
      if (field %in% c("tax_classification", "fx_direction")) shiny::updateSelectInput(session, id, selected = values[[field]])
      else shiny::updateTextInput(session, id, value = values[[field]])
    }
  }

  refresh_portfolio_exchange_staged <- function() {
    model<-portfolio_exchange_service$staged_imports();portfolio_exchange_staged_list(model)
    choices<-if(!length(model$imports))c("Keine vorgemerkten Pakete"="")else stats::setNames(vapply(model$imports,`[[`,character(1L),"staged_import_handle"),vapply(model$imports,function(item){statuses<-unlist(item$handoffs,use.names=FALSE);paste(item$record_count,"Datensätze ·",sum(statuses=="completed"),"von",length(statuses),"Übergaben abgeschlossen · Cash",item$cash_coverage_status)},character(1L)))
    selected<-if(length(model$imports))model$imports[[1L]]$staged_import_handle else "";shiny::updateSelectInput(session,"portfolio_exchange_staged_import",choices=choices,selected=selected);model
  }

  # Any new input starts a fresh Statement run: period, exchange or file (#322 retest).
  statement_exchange_cleared_upload <- shiny::reactiveVal(NULL)
  # Reward-Import aus der Ablage (#520): die uebernommenen Dateien des Instituts; der Eingang gibt das Institut vor.
  statement_exchange_archive <- shiny::reactiveVal(NULL)
  statement_exchange_archive_wanted <- shiny::reactiveVal(NULL)
  data_statement_archive_source_server_v1(input, output, session, "statement_exchange", statement_archive_service,
    on_take = function(frame) {
      upload <- input$statement_exchange_file; statement_exchange_cleared_upload(if (is.null(upload)) NULL else upload$datapath)
      statement_reset_run(); statement_exchange_archive(frame); statement_period_prefill()
    },
    accounts = function() { model <- asset_center_catalog(); if (is.null(model)) list() else model$accounts },
    resolve_id = function(ref) desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "account", ref),
    preselect = statement_exchange_archive_wanted, kinds = "transaction_export")
  # Eine eigene Datei oder eine andere Boerse verdraengt die Dateien aus der Ablage.
  shiny::observeEvent(input$statement_exchange_file, statement_exchange_archive(NULL), ignoreInit = TRUE)
  shiny::observeEvent(input$statement_exchange_adapter, statement_exchange_archive(NULL), ignoreInit = TRUE)
  statement_reset_run<-function(){
    statement_exchange_preview(NULL);statement_exchange_mapping(NULL);statement_exchange_selected_refs(NULL);reset_statement_reward_steps()
    statement_exchange_state(data_statement_exchange_preview_status_v1())
  }
  shiny::observeEvent(list(input$statement_exchange_period,input$statement_exchange_adapter,input$statement_exchange_file),statement_reset_run(),ignoreInit=TRUE)
  # Reward-Zeitraum (#462): mit der Datei ab dem juengsten gebuchten Reward dieser Boerse vorbelegen - nur solange der Beginn
  # noch auf der Vorgabe oder dem zuletzt vorbelegten Tag steht; eine eigene Wahl bleibt stehen. Gelesen wird erst hier, nicht beim Start.
  statement_period_auto <- shiny::reactiveVal(NULL); statement_period_note <- shiny::reactiveVal(NULL)
  statement_period_prefill <- function() {
    period <- shiny::isolate(input$statement_exchange_period); adapter <- shiny::isolate(input$statement_exchange_adapter)
    if ((is.null(shiny::isolate(input$statement_exchange_file)) && is.null(shiny::isolate(statement_exchange_archive()))) || length(period) != 2L) return(invisible())
    current <- as.character(as.Date(period[[1L]])); auto <- shiny::isolate(statement_period_auto())
    if (!identical(current, "2000-01-01") && !identical(current, auto)) return(invisible())
    latest <- tryCatch(securities_statement_service$latest("reward"), error = function(error) list())
    start <- data_reward_period_start_v1(latest, adapter, shiny::isolate(import_offered_reader(adapter, "reward"))$institution)
    if (is.null(start)) { statement_period_note(NULL); return(invisible()) }
    statement_period_auto(start)
    shiny::updateDateRangeInput(session, "statement_exchange_period", start = as.Date(start))
    statement_period_note(sprintf("Zeitraum ab dem jüngsten gebuchten Reward dieser Börse (%s) vorbelegt; an dem Tag schon gebuchte werden erkannt. Für ältere Zeilen den Beginn vorziehen.",
                                  format(as.Date(start), "%d.%m.%Y")))
  }
  shiny::observeEvent(list(input$statement_exchange_file, input$statement_exchange_adapter), statement_period_prefill(), ignoreInit = TRUE)
  output$statement_exchange_period_note <- shiny::renderUI({ note <- statement_period_note(); if (is.null(note)) NULL else shiny::p(class = "pl-section-copy", note) })
  shiny::observeEvent(input$statement_guided_restart,{
    # The browser keeps the last upload until a new file is chosen; remember it so
    # "Rewards anzeigen" cannot silently reuse the previous Statement.
    upload<-input$statement_exchange_file;statement_exchange_cleared_upload(if(is.null(upload))NULL else upload$datapath)
    statement_reset_run()
  })
  shiny::observeEvent(input$statement_exchange_preview_run, {
    upload<-input$statement_exchange_file;adapter<-input$statement_exchange_adapter;period<-input$statement_exchange_period
    if(!is.null(upload)&&identical(upload$datapath,statement_exchange_cleared_upload()))upload<-NULL
    archive<-statement_exchange_archive();archive_note<-NULL;archive_paths<-NULL
    if((is.null(upload)||is.null(upload$datapath)||!nzchar(upload$datapath))&&is.data.frame(archive)&&nrow(archive)>0L){
      # Aus der Ablage (#520, rc.343): alle CSV-Dateien dieser Boerse zusammen als ein Lauf, wie bei Auszuegen und Belegen. Bison
      # exportiert je Kalenderjahr; mit nur der juengsten Datei fehlten sonst die Rewards der Vorjahresdatei. Was in mehreren Dateien steht,
      # zaehlt der Leser einmal; was schon gebucht ist, erkennt die Zuordnung wie bei einer hochgeladenen Datei. Jede Datei wird vorab
      # einzeln probiert, damit eine fremde Datei nicht den ganzen Lauf verhindert.
      timezone<-""   # die Zeitzone des Lesers (#486)
      csv<-which(grepl("\\.csv$",archive$name,ignore.case=TRUE));readable<-integer();latest_day<-""
      for(index in csv){
        tried<-tryCatch(statement_mapping_center$exchange_preview(archive$datapath[[index]],adapter,timezone,as.Date("2000-01-01"),Sys.Date()),error=function(error)NULL)
        if(is.null(tried))next
        readable<-c(readable,index)
        days<-unlist(lapply(tried$rows,function(row)row$mapping_row$event_fields$local_date),use.names=FALSE)
        if(length(days))latest_day<-max(latest_day,as.character(days))
      }
      if(!length(readable)){statement_exchange_state(list(tone="warning",title="Keine passende Datei in der Ablage",copy="Keine der übernommenen Dateien ließ sich mit dem Leser dieser Börse lesen. Börse prüfen oder die Datei selbst wählen."));return()}
      archive_paths<-archive$datapath[readable]
      upload<-list(datapath=archive_paths[[1L]],name=archive$name[[readable[[1L]]]])
      skipped<-length(csv)-length(readable)
      archive_note<-paste0(if(length(readable)==1L)sprintf("Aus der Ablage: %s",archive$name[[readable[[1L]]]])else sprintf("Aus der Ablage: %d Dateien zusammen gelesen",length(readable)),
        sprintf(" (jüngster Reward %s)",if(nzchar(latest_day))format(as.Date(latest_day),"%d.%m.%Y")else"–"),
        if(skipped>0L)sprintf("; %d %s mit diesem Leser nicht lesbar und übergangen",skipped,if(skipped==1L)"Datei ist"else"Dateien sind")else"",".")
    }
    if(is.null(upload)||is.null(upload$datapath)||!nzchar(upload$datapath)){statement_exchange_state(list(tone="warning",title="Keine Datei gewählt",copy="Bitte zuerst die CSV-Datei der Börse auswählen oder Dateien aus der Ablage übernehmen."));return()}
    if(is.null(adapter)||!nzchar(adapter)) {
      statement_exchange_state(data_statement_exchange_preview_status_v1(error_code="data_statement_import_mapping_input_invalid"));return()
    }
    if(length(period)!=2L||any(is.na(as.Date(period)))||as.Date(period[[1L]])>as.Date(period[[2L]])) {
      statement_exchange_state(data_statement_exchange_preview_status_v1(error_code="statement_exchange_adapter_period_invalid"));return()
    }
    timezone<-""   # die Zeitzone nennt der Leser (#486); die Vorschau traegt sie an jeder Zeile
    tryCatch({
      preview<-if(length(archive_paths)>1L)statement_mapping_center$exchange_preview_many(archive_paths,adapter,timezone,as.Date(period[[1L]]),as.Date(period[[2L]]))
        else statement_mapping_center$exchange_preview(upload$datapath,adapter,timezone,as.Date(period[[1L]]),as.Date(period[[2L]]))
      if(!is.null(archive_note)&&isTRUE(preview$cross_file_duplicate_count>0L))
        archive_note<-paste(archive_note,if(as.integer(preview$cross_file_duplicate_count)==1L)"1 Zeile stand in mehreren Dateien und zählt einmal."
          else sprintf("%d Zeilen standen in mehreren Dateien und zählen einmal.",as.integer(preview$cross_file_duplicate_count)))
      statement_exchange_preview(preview);statement_exchange_mapping(NULL);statement_exchange_selected_refs(NULL);reset_statement_reward_steps();invisible(refresh_activity_catalog())
      profiles<-statement_mapping_center$profile_list(runtime$context,adapter,"1.0.0")$profiles
      reusable<-Filter(function(item)identical(item$profile_label,"Standardzuordnung"),profiles)
      profile<-if(length(reusable))statement_mapping_center$profile_read(runtime$context,reusable[[1L]]$profile_ref)else NULL
      statement_exchange_profile(profile);state<-data_statement_exchange_preview_status_v1(preview)
      if(!is.null(archive_note))state$copy<-paste(archive_note,state$copy)
      statement_exchange_state(state)
    },error=function(error){
      code<-if(!is.null(error$code))as.character(error$code)else"data_statement_import_mapping_boundary_failed"
      statement_exchange_preview(NULL);statement_exchange_mapping(NULL);reset_statement_reward_steps();statement_exchange_state(data_statement_exchange_preview_status_v1(error_code=code))
    })
  })
  statement_exchange_registry<-function(tuples,asset_refs,account_refs){
    selection<-.data_asset_activity_selection(activity_editor,runtime$context);assets<-list();accounts<-list()
    for(index in seq_len(nrow(tuples))){
      if(!nzchar(asset_refs[[index]])||!nzchar(account_refs[[index]]))next
      asset<-.data_asset_activity_resolve(selection,"assets",asset_refs[[index]]);account<-.data_asset_activity_resolve(selection,"accounts",account_refs[[index]])
      assets[[paste0("asset_option_",index)]]<-list(target_id=asset$asset_id)
      accounts[[paste0("account_option_",index)]]<-list(target_id=account$account_id,portfolio_id=account$portfolio_id)
    }
    list(assets=assets,accounts=accounts)
  }
  # Umfang je Portfolio (#551, Festlegung 11.11.2026): Zuordnungen auf ein Asset, dessen Klasse im Portfolio des gewaehlten Kontos nicht gewaehlt
  # ist. Alle Assets bleiben zuordenbar; uebersprungen wird mit "Noch nicht zuordnen".
  statement_exchange_scope<-shiny::reactive({
    value<-statement_exchange_preview();catalog<-activity_catalog();state<-portfolio_configuration$state()
    if(is.null(value)||is.null(catalog)||!is.list(state)||!is.list(state$portfolios)||!is.null(statement_exchange_handoff()))return(list())
    tuples<-data_statement_exchange_preview_tuples_v1(value);if(!nrow(tuples))return(list())
    selection<-tryCatch(.data_asset_activity_selection(activity_editor,runtime$context),error=function(error)NULL);if(is.null(selection))return(list())
    scopes<-stats::setNames(state$portfolios,vapply(state$portfolios,function(item)as.character(item$portfolio_id),character(1L)))
    classes<-portfolio_configuration$catalog();held<-list()
    for(index in seq_len(nrow(tuples))){
      asset_ref<-input[[paste0("statement_exchange_asset_",index)]];account_ref<-input[[paste0("statement_exchange_account_",index)]]
      if(!is.character(asset_ref)||length(asset_ref)!=1L||!nzchar(asset_ref)||!is.character(account_ref)||length(account_ref)!=1L||!nzchar(account_ref))next
      asset<-tryCatch(.data_asset_activity_resolve(selection,"assets",asset_ref),error=function(error)NULL)
      account<-tryCatch(.data_asset_activity_resolve(selection,"accounts",account_ref),error=function(error)NULL)
      scope<-if(is.list(account)&&is.character(account$portfolio_id))scopes[[account$portfolio_id]] else NULL
      if(!is.list(asset)||!is.list(scope)||isTRUE(asset$asset_type%in%as.character(unlist(scope$asset_types))))next
      held[[length(held)+1L]]<-list(index=index,rows=as.integer(tuples$Zeilen[[index]]),key=data_portfolio_configuration_class_key_v1(classes,asset$asset_type),
        label=data_portfolio_configuration_class_label_v1(classes,asset$asset_type),portfolio_id=account$portfolio_id,portfolio_label=as.character(scope$label))
    }
    held
  })
  output$statement_exchange_scope_ui<-shiny::renderUI({
    held<-statement_exchange_scope();if(!length(held))return(NULL)
    by_class<-split(vapply(held,function(item)item$rows,integer(1L)),vapply(held,function(item)item$label,character(1L)))
    listing<-paste(vapply(names(by_class),function(label)sprintf("%d × „%s“",sum(by_class[[label]]),label),character(1L)),collapse=", ")
    portfolios<-paste(unique(vapply(held,function(item)item$portfolio_label,character(1L))),collapse=", ")
    shiny::div(class="pl-field-group",
      portelyra_status_panel(sprintf("%d Reward(s) einer nicht gewählten Klasse",sum(vapply(held,function(item)item$rows,integer(1L)))),paste0(listing,
        " – im Portfolio „",portfolios,"“ nicht gewählt. Weiter geht es erst, wenn Sie entscheiden: die Klasse dazunehmen (über die Vorschau unter",
        " Einstellungen → Portfolio → Umfang dieses Portfolios) oder diese Zuordnungen auf „Noch nicht zuordnen“ setzen."),tone="warning"),
      shiny::div(class="pl-editor-actions",
        shiny::actionButton("statement_exchange_scope_add","Klasse dazunehmen",class="btn-default",onclick=data_settings_open_target_js_v1("portfolio-configuration-change")),
        shiny::actionButton("statement_exchange_scope_skip","Diese nicht zuordnen (überspringen)",class="btn-default")))
  })
  shiny::observeEvent(input$statement_exchange_scope_skip,{
    for(item in statement_exchange_scope())shiny::updateSelectInput(session,paste0("statement_exchange_asset_",item$index),selected="")
  })
  shiny::observeEvent(input$statement_exchange_scope_add,{
    held<-statement_exchange_scope();if(!length(held))return()
    shown<-portfolio_configuration$portfolio();targets<-unique(vapply(held,function(item)item$portfolio_id,character(1L)))
    if(!is.list(shown)||!identical(targets,shown$portfolio_id)){
      statement_exchange_state(list(tone="warning",title="Anderes Portfolio gewählt",copy=paste0("„Umfang dieses Portfolios“ zeigt das oben in „Assets pflegen“ gewählte Portfolio",
        if(is.list(shown))paste0(" „",shown$label,"“")else"",". Diese Rewards gehören zu „",paste(unique(vapply(held,function(item)item$portfolio_label,character(1L))),collapse=", "),
        "“ – bitte dort zuerst dieses Portfolio wählen.")));return()}
    portfolio_configuration$request_classes(setdiff(unique(vapply(held,function(item)item$key,character(1L))),"cash"))
  })
  shiny::observeEvent(input$statement_exchange_mapping_run, {
    preview<-statement_exchange_preview();catalog<-activity_catalog();adapter<-input$statement_exchange_adapter
    # Pflichtwahl (#551): erst dazunehmen oder nicht zuordnen.
    if(!is.null(preview)&&length(statement_exchange_scope())){statement_exchange_state(list(tone="warning",title="Erst entscheiden",copy=paste("Zuordnungen auf eine nicht gewählte Klasse:",
      "unten „Klasse dazunehmen“ oder „Diese nicht zuordnen (überspringen)“ wählen.")));return()}
    if(is.null(preview)||is.null(catalog)||is.null(adapter)||!nzchar(adapter))return()
    tuples<-data_statement_exchange_preview_tuples_v1(preview);mappings<-vector("list",nrow(tuples))
    for(index in seq_len(nrow(tuples))){
      asset_ref<-input[[paste0("statement_exchange_asset_",index)]];account_ref<-input[[paste0("statement_exchange_account_",index)]]
      mapped<-is.character(asset_ref)&&length(asset_ref)==1L&&nzchar(asset_ref)&&is.character(account_ref)&&length(account_ref)==1L&&nzchar(account_ref)
      mappings[[index]]<-list(source_asset_key=tuples$`Quell-Asset`[[index]],source_account_key=tuples$`Quellkonto`[[index]],event_type=tuples$Vorgang[[index]],disposition=if(mapped)"map"else"defer",target_asset_option_key=if(mapped)paste0("asset_option_",index)else NULL,target_account_option_key=if(mapped)paste0("account_option_",index)else NULL)
    }
    # Dieselbe Zeitzone wie in der Vorschau: die des Lesers (#486), an den Zeilen der Vorschau abzulesen.
    zones<-unique(unlist(lapply(preview$mapping_rows,function(row)row$event_fields$time_zone),use.names=FALSE))
    timezone<-if(length(zones)==1L&&is.character(zones)&&nzchar(zones))zones else "UTC"
    tryCatch({
      result<-statement_mapping_center$project(preview$mapping_rows,mappings,adapter,"1.0.0","EUR",timezone)
      reset_statement_reward_steps();statement_exchange_mapping(result);selected_refs<-list(asset_refs=vapply(seq_len(nrow(tuples)),function(index){value<-input[[paste0("statement_exchange_asset_",index)]];if(is.null(value))""else value},character(1L)),account_refs=vapply(seq_len(nrow(tuples)),function(index){value<-input[[paste0("statement_exchange_account_",index)]];if(is.null(value))""else value},character(1L)));statement_exchange_selected_refs(selected_refs)
      booked<-data_statement_reward_booked_match_v1(project_root,runtime$context,data_statement_reward_booked_candidates_v1(result,statement_exchange_registry(tuples,selected_refs$asset_refs,selected_refs$account_refs)));statement_exchange_booked(booked)
      status<-data_statement_import_mapping_status_v1(result);if(length(booked))status$copy<-paste(status$copy,sprintf("%d Rewards sind bereits gebucht und werden nicht erneut übernommen.",length(booked)))
      statement_exchange_state(status)
    },error=function(error){
      code<-if(!is.null(error$code))as.character(error$code)else"data_statement_import_mapping_boundary_failed"
      statement_exchange_state(data_statement_import_mapping_status_v1(error_code=code))
    })
  })
  # Guided Statement import (#322): two owner confirmations. "Vorbereiten" creates
  # the Drafts and validates them (no booking); "Buchen" commits exactly the
  # validated Rewards. Missing valuations and time collisions surface as special
  # cases in the same place. All sole-write authorities stay unchanged.
  statement_guided_counts<-function(batch){
    if(!is.list(batch)||!identical(batch$status,"reward_valuation_batch_ready"))return(NULL)
    rows<-batch$drafts;complete<-c("source_provided","owner_manual_complete","market_evidence_complete");open<-function(row)!identical(row$status,"committed")
    list(total=length(rows),
      pending=sum(vapply(rows,function(row)identical(row$valuation_summary$lifecycle,"valuation_pending")&&open(row),logical(1L))),
      blocked=sum(vapply(rows,function(row)identical(row$validation_status,"blocked")&&open(row),logical(1L))),
      unvalidated=sum(vapply(rows,function(row)row$valuation_summary$lifecycle%in%complete&&!row$validation_status%in%c("ready","blocked")&&open(row),logical(1L))),
      ready=sum(vapply(rows,function(row)row$valuation_summary$lifecycle%in%complete&&identical(row$validation_status,"ready")&&open(row),logical(1L))),
      committed=sum(vapply(rows,function(row)!open(row),logical(1L))))
  }
  statement_guided_new_count<-function(){mapping<-statement_exchange_mapping();if(is.null(mapping))return(0L);counts<-mapping$disposition_counts;max(0L,as.integer(counts$draft_ready)+as.integer(counts$draft_needs_valuation)-length(statement_exchange_booked()))}
  # Die Pruefung ist der langsamste Schritt des Imports: jede Revalidierung
  # rechnet eine eigene FIFO-Vorschau und braucht einige Sekunden, viele Rewards
  # also viele Minuten. Deshalb meldet sie Fortschritt und geschaetzte
  # Restzeit - ohne Meldung schwieg die Oberflaeche, und die Browserverbindung
  # brach ab (#422). Abgebrochen wird nur der laufende
  # Entwurf: jede fertige Pruefung steht als gespeicherte Draft-Revision und
  # bleibt beim naechsten Anlauf stehen.
  statement_guided_validate<-function(batch,report=NULL){
    counts<-statement_guided_counts(batch)
    # Auch blockierte erneut (rc.323): Ein Reward in der Sekunde einer gebuchten Buchung desselben Coins wird dabei versetzt.
    # Auch wenn noch Rewards ohne Kurs sind (#520): Die Pruefung nimmt nur bewertete; so werden fertige buchbar (Teilbuchung).
    if(is.null(counts)||counts$unvalidated+counts$blocked==0L)return(batch)
    preview<-data_activity_draft_preview_reward_batch_validation_v1(activity_draft_center,batch)
    if(identical(preview$status,"confirmation_required"))
      statement_reward_validation_result(data_activity_draft_apply_reward_batch_validation_v1(activity_draft_center,activity_editor,runtime$context,preview,TRUE,now_utc(),report))
    refresh_statement_reward_valuations()
  }
  # Eine eigene Fortschrittsanzeige fuer die Pruefung, getrennt vom Laden des
  # Stapels: beide Schritte brauchen unterschiedlich lange, und der Eigentuemer
  # soll sehen, bei welchem er steht. withProgress klammert den Aufruf ein und
  # raeumt die Anzeige in jedem Fall ab - mit einem eigenen Progress-Objekt blieb
  # sie nach dem letzten Entwurf stehen.
  statement_guided_validate_tracked<-function(batch){
    started<-Sys.time()
    shiny::withProgress(message="Rewards werden geprüft",value=0,detail="Vorschau wird gerechnet",{
      statement_guided_validate(batch,function(done,total){
        elapsed<-as.numeric(difftime(Sys.time(),started,units="secs"))
        remaining<-if(done>0L)round((elapsed/done)*(total-done)/60,1)else NA_real_
        detail<-if(done>=total)"fertig, Entwürfe werden gelesen" else if(!is.na(remaining)&&remaining>=0.5)sprintf("%d von %d · noch etwa %s Minuten",done,total,format(remaining,nsmall=1))else sprintf("%d von %d",done,total)
        shiny::setProgress(value=done/total,detail=detail)
      })
    })
  }
  statement_guided_market_check<-function(batch){
    counts<-statement_guided_counts(batch)
    if(is.null(counts)||counts$pending==0L){statement_reward_market_batch_preview(NULL);return(invisible(NULL))}
    statement_reward_market_batch_preview(tryCatch(data_activity_draft_preview_reward_market_batch_v1(activity_draft_center,statement_reward_market_service,runtime$context,batch),error=function(error)NULL))
  }
  statement_guided_summary<-function(batch,booked){
    counts<-statement_guided_counts(batch);if(is.null(counts))return(NULL)
    extra<-c(if(counts$pending>0L)sprintf("%d ohne Kurs – bitte unten ergänzen",counts$pending),if(counts$blocked>0L)sprintf("%d blockiert – Grund unten anzeigen und klären",counts$blocked))
    list(tone=if(length(extra))"warning"else"neutral",title="Rewards vorbereitet und geprüft",
      copy=paste(c(sprintf("%d bereit zum Buchen",counts$ready),if(booked>0L)sprintf("%d bereits gebucht",booked),extra,"noch keine Buchung"),collapse=" · "))
  }
  shiny::observeEvent(input$statement_guided_prepare_run,{
    preview<-statement_exchange_preview();projection<-statement_exchange_mapping();selected<-statement_exchange_selected_refs();catalog<-activity_catalog()
    if(is.null(preview)||is.null(projection)||is.null(selected)||is.null(catalog))return()
    if(length(statement_exchange_scope())){statement_guided_result(list(tone="warning",title="Erst entscheiden",copy=paste("Zuordnungen auf eine nicht gewählte Klasse:",
      "„Klasse dazunehmen“ oder „Diese nicht zuordnen (überspringen)“ wählen, dann die Zuordnung erneut prüfen.")));return()}
    tuples<-data_statement_exchange_preview_tuples_v1(preview)
    current_assets<-vapply(seq_len(nrow(tuples)),function(index){value<-input[[paste0("statement_exchange_asset_",index)]];if(is.null(value))""else value},character(1L));current_accounts<-vapply(seq_len(nrow(tuples)),function(index){value<-input[[paste0("statement_exchange_account_",index)]];if(is.null(value))""else value},character(1L))
    if(!identical(current_assets,selected$asset_refs)||!identical(current_accounts,selected$account_refs)){
      statement_guided_result(list(tone="warning",title="Zuordnung wurde geändert",copy="Bitte die Zuordnung erneut prüfen; danach wieder vorbereiten."));statement_exchange_mapping(NULL);return()
    }
    tryCatch({
      registry<-statement_exchange_registry(tuples,selected$asset_refs,selected$account_refs)
      booked<-data_statement_reward_booked_match_v1(project_root,runtime$context,data_statement_reward_booked_candidates_v1(projection,registry));statement_exchange_booked(booked)
      result<-shiny::withProgress(message="Rewards werden vorbereitet",value=0,{data_statement_import_mapping_handoff_v1(projection,activity_draft_center,runtime$context,registry,portfolio_id=NULL,source_fingerprint=preview$source_fingerprint,now_utc=now_utc(),progress_callback=function(done,total)shiny::setProgress(done/total,detail=paste(done,"von",total)),booked_row_keys=booked)})
      statement_exchange_handoff(result)
      # The confirmed mapping is remembered for the next Statement of this exchange.
      try(statement_save_profile(),silent=TRUE)
      loaded<-shiny::withProgress(message="Entwürfe werden gelesen",value=0,{refresh_statement_reward_valuations(function(done,total)shiny::setProgress(done/total,detail=paste(done,"von",total)))})
      batch<-statement_guided_validate_tracked(loaded)
      statement_guided_market_check(batch)
      statement_guided_result(statement_guided_summary(batch,length(booked)))
    },error=function(error){
      code<-if(!is.null(error$code))as.character(error$code)else"data_statement_import_mapping_boundary_failed"
      statement_guided_result(list(tone="error",title="Vorbereitung nicht möglich",copy=data_statement_import_mapping_user_message_v1(code)))
    })
  })
  shiny::observeEvent(input$statement_guided_revalidate_run,{
    batch<-statement_reward_valuation_batch();if(is.null(statement_guided_counts(batch)))return()
    statement_guided_result(NULL)
    tryCatch({batch<-statement_guided_validate_tracked(refresh_statement_reward_valuations());statement_guided_market_check(batch);statement_guided_result(statement_guided_summary(batch,length(statement_exchange_booked())))},
      error=function(error)statement_guided_result(data_statement_reward_error_v1("validate",error)))
  })
  # Apply every available stored valuation at once, then validate again (#322 retest).
  shiny::observeEvent(input$statement_guided_market_all_run,{
    preview<-statement_reward_market_batch_preview();if(is.null(preview)||!identical(preview$status,"confirmation_required"))return()
    tryCatch({
      result<-shiny::withProgress(message="Bewertungen werden übernommen",value=0,{data_activity_draft_apply_reward_market_batch_v1(activity_draft_center,statement_reward_market_service,runtime$context,preview,TRUE,now_utc(),progress_callback=function(done,total)shiny::setProgress(done/total,detail=paste(done,"von",total)))})
      statement_reward_market_batch_result(result)
      batch<-statement_guided_validate_tracked(refresh_statement_reward_valuations());statement_guided_market_check(batch)
      summary<-statement_guided_summary(batch,length(statement_exchange_booked()));summary$title<-sprintf("%d Bewertungen übernommen",as.integer(result$valuation_applied_count));statement_guided_result(summary)
    },error=function(error)statement_guided_result(list(tone="error",title="Bewertungen nicht übernommen",copy="Die gespeicherten Kurse konnten nicht übernommen werden; es wurde nichts gebucht.")))
  })
  # Buchen ist fuer den gefuehrten Weg und fuer einen fortgesetzten Lauf dasselbe;
  # der Stapel ist gespeichert, nicht an die Sitzung gebunden. Der Fingerprint wird
  # ausdruecklich uebergeben, weil beim Fortsetzen kein Statement vorliegt.
  # Pruefstand (rc.380): Reward-Exporte nennen keinen Saldo; solange der Leser in diesem Portfolio nicht an Ihren Belegen geprueft ist, warnt
  # die Karte deutlich und bucht nur mit Haekchen. Nach dem Buchen wird der Stand fuer genau diesen Plugin-Code festgehalten.
  statement_reward_reader_refresh <- shiny::reactiveVal(0L)
  statement_reward_reader_check <- shiny::reactive({
    statement_reward_reader_refresh()
    adapter <- input$statement_exchange_adapter
    if (!is.character(adapter) || length(adapter) != 1L || !nzchar(adapter)) return(NULL)
    batch <- statement_reward_valuation_batch()
    if (is.null(statement_exchange_preview()) && is.null(statement_guided_counts(batch))) return(NULL)
    # Portfolios getrennt (Festlegung 09.11.2026): die Konten der vorbereiteten Rewards; vorher nur, wenn es genau ein Portfolio gibt.
    accounts <- attr(batch, "account_ids"); if (is.null(accounts)) accounts <- character()
    tryCatch(statement_reader_check_service$status(list(list(reader_id = adapter, domain = "reward")), accounts, balance_checked = FALSE),
      error = function(error) {
        code <- if (is.null(error$code)) "statement_reader_check_store_invalid" else as.character(error$code)
        if (identical(code, "statement_reader_check_portfolio_unknown") && !length(accounts)) return(NULL)   # erst nach der Zuordnung bekannt
        list(status = "unavailable", code = code, acknowledgment_required = TRUE, notes = list(), hints = list())
      })
  })
  output$statement_reward_reader_check <- shiny::renderUI({
    check <- statement_reward_reader_check()
    if (!is.list(check)) return(NULL)
    shiny::tagList(data_statement_reader_check_panel_v1(check), data_statement_reader_check_ack_v1("statement_reward_reader_ack", check, "dem Export"))
  })
  statement_guided_book<-function(source_fingerprint=NULL,adapter_id=shiny::isolate(input$statement_exchange_adapter)){
    batch<-statement_reward_valuation_batch();counts<-statement_guided_counts(batch)
    # Teilbuchung (#520, Festlegung 28.10.2026): Fertige Rewards werden gebucht, blockierte und unbewertete bleiben offen.
    if(is.null(counts)||counts$ready==0L)return()
    reader_pairs <- list(list(reader_id = adapter_id, domain = "reward")); acknowledged <- isTRUE(shiny::isolate(input$statement_reward_reader_ack))
    reward_accounts <- attr(batch, "account_ids"); if (is.null(reward_accounts)) reward_accounts <- character()
    checked <- tryCatch({ statement_reader_check_service$require(reader_pairs, acknowledged, reward_accounts); TRUE }, error = function(error) {
      code <- if (is.null(error$code)) "statement_reader_check_store_invalid" else as.character(error$code)
      reader <- data_statement_reader_message_v1(code, adapter_id, "Es wurde nichts gebucht.")
      statement_guided_result(if (is.null(reader)) data_statement_reward_error_v1("book", error) else list(tone = "warning", title = reader$title, copy = reader$copy, code = code))
      FALSE })
    if (!isTRUE(checked)) return()
    tryCatch({
      preview<-data_activity_draft_preview_reward_canonical_batch_v1(activity_draft_center,batch)
      if(!identical(preview$status,"confirmation_required")){statement_guided_result(list(tone="warning",title="Nichts zu buchen",copy="Es liegen keine geprüften Rewards vor."));return()}
      gestartet<-Sys.time()
      result<-shiny::withProgress(message="Rewards werden gebucht",value=0,detail="Erster Reward wird geprüft",{
        data_activity_draft_apply_reward_canonical_batch_v1(activity_draft_center,activity_editor,runtime$context,preview,TRUE,now_utc(),function(done,total){
          vergangen<-as.numeric(difftime(Sys.time(),gestartet,units="secs"))
          rest<-if(done>0L)round((vergangen/done)*(total-done)/60,1)else NA_real_
          detail<-if(done>=total)"fertig, Bestand wird gelesen" else if(!is.na(rest)&&rest>=0.5)sprintf("%d von %d gebucht · noch etwa %s Minuten",done,total,format(rest,nsmall=1))else sprintf("%d von %d gebucht",done,total)
          shiny::setProgress(value=done/total,detail=detail)
        })})
      statement_reward_canonical_result(result);invisible(refresh_statement_reward_valuations(source_fingerprint=source_fingerprint))
      if(isTRUE(result$canonical_write)){portfolio_completion_notice(list(status="update_required",committed_count=result$canonical_committed_count));try(realized_model(realized_adapter$read(runtime$context)),silent=TRUE)}
      # Kennung der Boerse in den Belegspeicher (rc.345): aus der geladenen Datei und aus der Ablage. Fehlt sie, fehlt sie im Steuerreport.
      upload<-shiny::isolate(input$statement_exchange_file)
      references<-if(isTRUE(result$canonical_write))data_statement_reward_references_record_v1(project_root,runtime$context,adapter_id,
        if(is.data.frame(upload))as.character(upload$datapath)else character(),now_utc())else NULL
      booked<-length(statement_exchange_booked())
      reader_recorded <- if (isTRUE(result$canonical_write)) tryCatch(statement_reader_check_service$record(reader_pairs, acknowledged, now_utc(), reward_accounts,
          document_count = if (is.data.frame(upload)) nrow(upload) else NULL, booking_count = result$canonical_committed_count),
        error = function(error) paste0("failed:", if (is.null(error$code)) "statement_reader_check_store_invalid" else error$code)) else NULL
      statement_reward_reader_refresh(statement_reward_reader_refresh() + 1L)
      statement_guided_result(list(tone=if(result$blocked_count>0L)"warning"else"positive",title=if(result$blocked_count>0L)"Teilweise gebucht"else"Rewards gebucht",
        copy=paste(c(sprintf("%d Rewards gebucht",result$canonical_committed_count),if(isTRUE(result$shifted_count>0L))sub("^ · ","",data_activity_draft_shift_note_v1(result$shifted_count)),if(booked>0L)sprintf("%d waren bereits vorhanden",booked),if(result$blocked_count>0L)sprintf("%d nicht gebucht – Grund unten unter „Blockierte Rewards“",result$blocked_count),data_statement_reward_references_note_v1(references),Filter(nzchar,data_statement_reader_check_note_v1(reader_recorded)),"Weiter: Portfolio-Stand aktualisieren"),collapse=" · ")))
    },error=function(error)statement_guided_result(data_statement_reward_error_v1("book",error)))
  }
  shiny::observeEvent(input$statement_guided_book_run,statement_guided_book())
  # Offene Reward-Entwuerfe aus frueheren Laeufen. Sie sind gespeichert und
  # ueberleben jeden Verbindungsabbruch; bis hierher zeigte die Karte sie nicht,
  # und nach einem Abbruch stand man wieder auf Schritt 1, ohne zu
  # wissen, wieviel bereits geprueft war (#422). Die Gruppe wird ueber
  # ihren Platz in der Liste angesprochen, nicht ueber den Quell-Fingerprint - der
  # bleibt der Oberflaeche verborgen.
  # Name der Boerse: das Institut des Reward-Lesers aus der Leserliste (#486).
  statement_exchange_label<-function(adapter_id){
    if(!is.character(adapter_id)||length(adapter_id)!=1L||is.na(adapter_id))return("Unbekannte Börse")
    reader<-shiny::isolate(import_offered_reader(adapter_id,"reward"))
    if(is.null(reader))import_offered_load()
    reader<-shiny::isolate(import_offered_reader(adapter_id,"reward"))
    if(is.list(reader)&&is.character(reader$institution)&&nzchar(reader$institution))reader$institution else adapter_id
  }
  statement_resume_date<-function(value){
    if(!is.character(value)||length(value)!=1L||is.na(value))return("unbekannt")
    formatted<-tryCatch(format(as.Date(value),"%d.%m.%Y"),error=function(error)NA_character_)
    if(is.na(formatted))value else formatted
  }
  refresh_statement_resume_groups<-function(){
    statement_resume_groups(tryCatch(data_activity_draft_reward_sources_v1(activity_draft_center,runtime$context),error=function(error)list()))
  }
  # Vorschau zum Stilllegen eines erledigten Laufs (#520): bleibt bis zur Bestaetigung oder zum Abbruch stehen.
  statement_retire_preview<-shiny::reactiveVal(NULL)
  shiny::observeEvent(input$statement_resume_retire,{
    group<-statement_resume_group(input$statement_resume_retire);if(is.null(group))return()
    statement_resume_notice(NULL)
    statement_retire_preview(tryCatch(data_activity_draft_retire_preview_v1(activity_draft_center,runtime$context,group,now_utc()),error=function(error){
      statement_resume_notice(list(tone="error",title="Stilllegen nicht möglich",copy="Die Vorschau ließ sich nicht erstellen; am Lauf hat sich nichts geändert. Bitte „Stand neu lesen“."));NULL}))
  },ignoreInit=TRUE)
  shiny::observeEvent(input$statement_resume_retire_cancel,statement_retire_preview(NULL),ignoreInit=TRUE)
  shiny::observeEvent(input$statement_resume_retire_confirm,{
    preview<-statement_retire_preview();if(is.null(preview))return()
    statement_retire_preview(NULL)
    done<-tryCatch({data_activity_draft_retire_apply_v1(activity_draft_center,runtime$context,preview,now_utc());TRUE},error=function(error)FALSE)
    statement_resume_notice(if(done)list(tone="positive",title="Lauf stillgelegt",copy=sprintf("%d Entwürfe sind erledigt und erscheinen nicht mehr. Gebuchtes ist unverändert.",preview$open_count))
      else list(tone="error",title="Stilllegen nicht möglich",copy="Es wurde nichts geändert. Bitte „Stand neu lesen“ und erneut versuchen."))
    refresh_statement_resume_groups()
  },ignoreInit=TRUE)
  statement_resume_group<-function(index){
    groups<-statement_resume_groups()
    if(!is.list(groups)||!is.numeric(index)||length(index)!=1L||is.na(index)||index<1L||index>length(groups))return(NULL)
    groups[[as.integer(index)]]
  }
  output$statement_resume_summary<-shiny::renderUI({
    groups<-statement_resume_groups()
    if(is.null(groups))return(shiny::span("Was aus früheren Läufen noch offen ist"))
    if(!length(groups))return(shiny::span("Frühere Läufe: nichts offen"))
    wartend<-Filter(function(group)is.na(group$covered_by),groups)
    if(!length(wartend))return(shiny::span(sprintf("Frühere Läufe: nichts zu tun (%d erledigt)",length(groups))))
    offen<-sum(vapply(wartend,function(group)group$total,integer(1L)))
    shiny::span(shiny::strong(sprintf("Aus früheren Läufen offen: %d Reward-Entwürfe",offen)),
      sprintf(" in %d %s – hier öffnen",length(wartend),if(length(wartend)==1L)"Lauf"else"Läufen"))
  })
  output$statement_resume_state<-shiny::renderUI({
    groups<-statement_resume_groups();notice<-statement_resume_notice();active<-statement_resume_active()
    if(is.null(groups))return(shiny::div(class="pl-editor-actions",
      shiny::actionButton("statement_resume_refresh","Nachsehen, was aus früheren Läufen offen ist",class="btn-default"),
      shiny::span(class="pl-field-hint","Liest nur die gespeicherten Entwürfe. Keine Datei, keine Buchung.")))
    if(!length(groups))return(shiny::div(class="pl-editor-actions",
      shiny::span(class="pl-field-hint","Keine offenen Reward-Entwürfe aus früheren Läufen."),
      shiny::actionButton("statement_resume_refresh","Erneut nachsehen",class="btn-default")))
    # Erledigte Laeufe stehen getrennt und ohne Schaltflaechen: ihre Rewards
    # stecken restlos in einem groesseren Lauf. Sonst standen alle Laeufe gleichberechtigt da, und die Karte forderte auch bei den ueberfluessigen
    # zum Handeln auf (#422).
    offen_index<-Filter(function(index)is.na(groups[[index]]$covered_by),seq_along(groups))
    erledigt_index<-setdiff(seq_along(groups),offen_index)
    karte<-function(index){
      group<-groups[[index]];running<-identical(active,index)
      zahlen<-paste(c(sprintf("%d bereit",group$ready),if(group$unvalidated>0L)sprintf("%d ungeprüft",group$unvalidated),
        if(group$pending>0L)sprintf("%d ohne Kurs",group$pending),if(group$blocked>0L)sprintf("%d blockiert",group$blocked),
        if(group$committed>0L)sprintf("%d gebucht",group$committed)),collapse=" · ")
      shiny::div(class="pl-write-boundary",
        shiny::p(shiny::strong(sprintf("%s · %d Entwürfe",statement_exchange_label(group$adapter_id),group$total)),
          shiny::br(),sprintf("Rewards vom %s bis %s",statement_resume_date(group$first_date),statement_resume_date(group$last_date)),
          shiny::br(),zahlen),
        shiny::div(class="pl-editor-actions",
          # Auch nur blockierte Entwuerfe lassen sich erneut pruefen (#520); ohne Kurs geht es erst nach "Kurs ergaenzen".
          if(group$unvalidated>0L||(group$blocked>0L&&group$pending==0L))shiny::tags$button(type="button",class="btn btn-primary",
            onclick=sprintf("Shiny.setInputValue('statement_resume_validate',%d,{priority:'event'});return false;",index),
            if(group$unvalidated>0L)sprintf("%d Entwürfe weiter prüfen",group$unvalidated+group$blocked)else sprintf("%d blockierte Entwürfe erneut prüfen",group$blocked))else NULL,
          if(group$ready>0L)shiny::tags$button(type="button",class=if(group$unvalidated+group$pending+group$blocked==0L)"btn btn-primary"else"btn btn-default",
            onclick=sprintf("Shiny.setInputValue('statement_resume_book',%d,{priority:'event'});return false;",index),
            if(group$unvalidated+group$pending+group$blocked==0L)sprintf("%d geprüfte Rewards buchen",group$ready)
            else sprintf("%d fertige buchen – %d bleiben offen",group$ready,group$unvalidated+group$pending+group$blocked))else NULL,
          if(isTRUE(group$retire_by_owner))shiny::tags$button(type="button",class="btn btn-default",
            onclick=sprintf("Shiny.setInputValue('statement_resume_retire',%d,{priority:'event'});return false;",index),
            sprintf("Rest (%d) als von Hand gebucht stilllegen",group$blocked+group$pending))else NULL,
          shiny::tags$button(type="button",class="btn btn-default",
            onclick=sprintf("Shiny.setInputValue('statement_resume_open',%d,{priority:'event'});return false;",index),
            "Diese Entwürfe unten anzeigen"),
          if(running)shiny::span(class="pl-field-hint","Dieser Stapel ist unten geladen.")else NULL),
        if(group$pending>0L)shiny::p(class="pl-field-hint",sprintf("%d Rewards brauchen zuerst einen Wert in EUR; dafür unten „Kurs ergänzen“ benutzen.",group$pending))else NULL,
        if(group$blocked>0L)shiny::p(class="pl-field-hint",sprintf("%d Rewards sind blockiert. Erneut prüfen löst den häufigsten Fall (gleiche Sekunde wie eine gebuchte Buchung); den Grund der übrigen zeigt unten „Blockierte Rewards“.",group$blocked))else NULL)
    }
    erledigt_zeile<-function(index){
      group<-groups[[index]]
      grund<-if(isTRUE(group$already_booked))sprintf("alle %d Rewards sind bereits gebucht",group$total)
        else sprintf("alle %d stecken auch im Lauf mit %d Entwürfen",group$total,group$covered_by_total)
      # Stilllegen (#520): nur mit eindeutigem Ersatzlauf; der Quell-Fingerprint bleibt serverseitig, der Knopf nennt den Platz.
      retire<-if(is.character(group$retire_replacement)&&!is.na(group$retire_replacement))shiny::tags$button(type="button",class="btn btn-default btn-sm",
        onclick=sprintf("Shiny.setInputValue('statement_resume_retire',%d,{priority:'event'});return false;",index),"Lauf stilllegen")else NULL
      shiny::tags$li(sprintf("%s · %d Entwürfe vom %s bis %s – %s ",
        statement_exchange_label(group$adapter_id),group$total,statement_resume_date(group$first_date),
        statement_resume_date(group$last_date),grund),retire)
    }
    retire_preview<-statement_retire_preview()
    retire_panel<-if(is.list(retire_preview))shiny::div(class="pl-write-boundary",
      portelyra_status_panel(sprintf("%d Entwürfe stilllegen?",retire_preview$open_count),
        paste(c(if(isTRUE(retire_preview$by_owner))"Nur bestätigen, wenn Sie diese Rewards von Hand in „Manuell“ gebucht haben – Portelyra kann das nicht prüfen. Sonst fehlen sie im Bestand.",
          "Die Entwürfe dieses Laufs werden als erledigt markiert und verschwinden aus der Liste. Nichts wird gebucht oder gelöscht; die Entwürfe bleiben als abgelöste Fassung erhalten.",
          if(retire_preview$committed_count>0L)sprintf("Die %d schon gebuchten Rewards dieses Laufs bleiben unverändert.",retire_preview$committed_count)),collapse=" "),tone="warning"),
      shiny::div(class="pl-editor-actions",
        shiny::actionButton("statement_resume_retire_confirm","Stilllegen bestätigen",class="btn-primary"),
        shiny::actionButton("statement_resume_retire_cancel","Abbrechen",class="btn-default")))else NULL
    zu_tun<-sum(vapply(offen_index,function(index)groups[[index]]$total,integer(1L)))
    shiny::tagList(
      if(length(offen_index))shiny::tagList(
        shiny::p(class="pl-section-copy",
          shiny::strong(sprintf("%d Reward-Entwürfe warten in %d %s.",zu_tun,length(offen_index),
            if(length(offen_index)==1L)"Lauf"else"Läufen")),
          " Sie sind auf diesem Rechner gespeichert und unabhängig vom Browser; ein abgebrochener Lauf geht hier weiter, ohne die Datei erneut vorzulegen."),
        lapply(offen_index,karte))
      else shiny::p(class="pl-section-copy","Kein Lauf wartet auf eine Fortsetzung."),
      if(length(erledigt_index))shiny::tagList(
        shiny::tags$h4("Erledigt – hier ist nichts zu tun"),
        shiny::p(class="pl-section-copy",
          "Jeder Reward dieser Läufe ist schon gebucht oder steckt vollständig in einem größeren Lauf. Sie zu buchen würde dieselben Rewards doppelt eintragen."),
        shiny::tags$ul(lapply(erledigt_index,erledigt_zeile)))else NULL,
      retire_panel,
      if(!is.null(notice))shiny::tagList(portelyra_status_panel(notice$title,notice$copy,tone=notice$tone),data_statement_reward_error_code_ui_v1(notice))else NULL,
      shiny::div(class="pl-editor-actions",shiny::actionButton("statement_resume_refresh","Stand neu lesen",class="btn-default")))
  })
  shiny::observeEvent(input$statement_resume_refresh,{statement_resume_notice(NULL);refresh_statement_resume_groups()})
  # Einmal je Sitzung lesen, damit der Stand ohne Knopfdruck dasteht. Bei vielen Entwuerfen kostete das mehrere Sekunden: Die Liste
  # liest jede Entwurfsdatei. Ohne ignoreInit, aus demselben
  # Grund wie beim Cash-Stand: Der Reiter ist beim Start schon offen.
  statement_resume_loaded <- FALSE
  shiny::observeEvent(input$asset_center_step,{
    if(!statement_resume_loaded&&identical(input$asset_center_step,"transactions")){statement_resume_loaded<<-TRUE;refresh_statement_resume_groups()}
  },priority=-100L)
  statement_resume_load<-function(index,validate){
    group<-statement_resume_group(index);if(is.null(group))return()
    statement_resume_active(as.integer(index))
    tryCatch({
      loaded<-shiny::withProgress(message="Entwürfe werden gelesen",value=0,{refresh_statement_reward_valuations(function(done,total)shiny::setProgress(done/total,detail=paste(done,"von",total)),source_fingerprint=group$source_fingerprint)})
      batch<-if(isTRUE(validate))statement_guided_validate_tracked(loaded)else loaded
      statement_guided_market_check(batch)
      counts<-statement_guided_counts(batch)
      statement_resume_notice(if(is.null(counts))list(tone="warning",title="Keine Entwürfe gefunden",copy="Für diese Quelle liegt kein Stapel mehr vor.")else
        list(tone=if(counts$ready>0L&&counts$unvalidated==0L&&counts$pending==0L&&counts$blocked==0L)"positive"else"warning",
          title=sprintf("%s · %d Entwürfe geladen",statement_exchange_label(group$adapter_id),counts$total),
          copy=paste(c(sprintf("%d bereit zum Buchen",counts$ready),if(counts$unvalidated>0L)sprintf("%d noch ungeprüft",counts$unvalidated),
            if(counts$pending>0L)sprintf("%d ohne Kurs",counts$pending),if(counts$blocked>0L)sprintf("%d blockiert",counts$blocked),"noch keine Buchung"),collapse=" · ")))
      refresh_statement_resume_groups()
    },error=function(error)statement_resume_notice(data_statement_reward_error_v1("resume",error)))
  }
  shiny::observeEvent(input$statement_resume_validate,statement_resume_load(input$statement_resume_validate,TRUE),ignoreInit=TRUE)
  shiny::observeEvent(input$statement_resume_open,statement_resume_load(input$statement_resume_open,FALSE),ignoreInit=TRUE)
  shiny::observeEvent(input$statement_resume_book,{
    group<-statement_resume_group(input$statement_resume_book);if(is.null(group))return()
    statement_resume_active(as.integer(input$statement_resume_book))
    tryCatch({
      invisible(refresh_statement_reward_valuations(source_fingerprint=group$source_fingerprint))
      statement_guided_book(group$source_fingerprint,group$adapter_id)
      result<-statement_guided_result()
      statement_resume_notice(if(is.null(result))NULL else list(tone=result$tone,title=result$title,copy=result$copy,code=result$code))
      refresh_statement_resume_groups()
    },error=function(error)statement_resume_notice(data_statement_reward_error_v1("book",error)))
  },ignoreInit=TRUE)
  shiny::observeEvent(input$statement_reward_valuation_select, {
    handle<-input$statement_reward_valuation_select
    if(is.character(handle)&&length(handle)==1L&&nzchar(handle))tryCatch(statement_reward_valuation_open(data_activity_draft_open_v1(activity_draft_center,activity_editor,runtime$context,handle)),error=function(error)statement_reward_valuation_open(NULL))
  },ignoreInit=TRUE)
  shiny::observeEvent(input$statement_reward_collision_prepare, {
    batch<-statement_reward_valuation_batch();if(is.null(batch))return()
    tryCatch({statement_reward_collision_preview(data_activity_draft_preview_reward_collision_batch_v1(activity_draft_center,batch));statement_reward_collision_result(NULL);shiny::updateCheckboxInput(session,"statement_reward_collision_confirm",value=FALSE)},error=function(error){statement_reward_collision_preview(NULL);statement_reward_collision_result(list(status="error",error_code=if(is.null(error$code))"data_activity_draft_adapter_failed"else error$code))})
  })
  shiny::observeEvent(input$statement_reward_collision_apply, {
    preview<-statement_reward_collision_preview();if(is.null(preview)||!identical(preview$status,"confirmation_required"))return()
    tryCatch({result<-shiny::withProgress(message="Gemeinsamer FIFO-Nachweis wird vorbereitet",value=0,{data_activity_draft_apply_reward_collision_batch_v1(activity_draft_center,activity_editor,runtime$context,preview,isTRUE(input$statement_reward_collision_confirm),now_utc(),function(done,total)shiny::setProgress(done/total,detail=paste(done,"von",total)))});statement_reward_collision_result(result);statement_reward_collision_preview(NULL);shiny::updateCheckboxInput(session,"statement_reward_collision_confirm",value=FALSE);invisible(refresh_statement_reward_valuations())},error=function(error){statement_reward_collision_result(list(status="error",error_code=if(is.null(error$code))"data_activity_draft_adapter_failed"else error$code))})
  })
  shiny::observeEvent(input$statement_reward_market_prepare, {
    model<-statement_reward_valuation_open();if(is.null(model))return()
    tryCatch({p<-data_activity_draft_preview_market_reward_valuation_v1(activity_draft_center,statement_reward_market_service,runtime$context,model$draft_handle);statement_reward_market_preview(p)},error=function(error){statement_reward_market_preview(list(error_code=if(is.null(error$code))'data_reward_daily_close_boundary_failed'else error$code))})
  })
  shiny::observeEvent(input$statement_reward_market_apply, {
    model<-statement_reward_valuation_open();p<-statement_reward_market_preview();if(is.null(model)||is.null(p)||!is.null(p$error_code))return()
    tryCatch({data_activity_draft_set_market_reward_valuation_v1(activity_draft_center,statement_reward_market_service,runtime$context,model$draft_handle,isTRUE(input$statement_reward_market_confirm),now_utc());statement_reward_market_preview(NULL);invisible(refresh_statement_reward_valuations())},error=function(error){statement_reward_market_preview(list(error_code=if(is.null(error$code))'data_reward_daily_close_boundary_failed'else error$code))})
  })
  shiny::observeEvent(input$statement_reward_valuation_apply, {
    model<-statement_reward_valuation_open();if(is.null(model))return()
    tryCatch({
      data_activity_draft_set_manual_reward_valuation_v1(activity_draft_center,statement_mapping_center,runtime$context,model$draft_handle,input$statement_reward_valuation_mode,input$statement_reward_valuation_value,input$statement_reward_valuation_currency,now_utc())
      data_activity_draft_revalidate_v1(activity_draft_center,activity_editor,runtime$context,model$draft_handle,now_utc())
      invisible(refresh_statement_reward_valuations())
    },error=function(error){statement_reward_valuation_batch(list(status="error",error_code=if(!is.null(error$code))as.character(error$code)else"data_statement_import_mapping_boundary_failed"))})
  })
  statement_save_profile<-function(){
    preview<-statement_exchange_preview();projection<-statement_exchange_mapping();selected<-statement_exchange_selected_refs();catalog<-activity_catalog();adapter<-input$statement_exchange_adapter
    if(is.null(preview)||is.null(projection)||is.null(selected)||is.null(catalog)||is.null(adapter)||!nzchar(adapter))return(invisible(NULL))
    tuples<-data_statement_exchange_preview_tuples_v1(preview)
    selection<-.data_asset_activity_selection(activity_editor,runtime$context)
    rows<-data_statement_import_mapping_profile_rows_v1(tuples,selected$asset_refs,selected$account_refs,function(ref).data_asset_activity_resolve(selection,"assets",ref)$asset_id,function(ref).data_asset_activity_resolve(selection,"accounts",ref)$account_id)
    previous<-statement_exchange_profile();saved<-statement_mapping_center$profile_save(runtime$context,adapter,"1.0.0","Standardzuordnung",rows,now_utc(),if(is.null(previous))NULL else previous$profile_ref,if(is.null(previous))NULL else previous$revision)
    statement_exchange_profile(statement_mapping_center$profile_read(runtime$context,saved$profile_ref))
    invisible(saved)
  }
  shiny::observeEvent(input$statement_mapping_run, {
    scenario<-input$statement_mapping_scenario
    tryCatch({
      result<-data_statement_import_mapping_synthetic_v1(statement_mapping_center,scenario)
      statement_mapping_result(result);statement_mapping_state(data_statement_import_mapping_status_v1(result))
    },error=function(error){
      code<-if(!is.null(error$code))error$code else "data_statement_import_mapping_boundary_failed"
      statement_mapping_state(data_statement_import_mapping_status_v1(error_code=code))
    })
  })
  shiny::observeEvent(input$statement_workspace_run, {
    scenario<-input$statement_workspace_scenario
    if(is.null(scenario)||!nzchar(scenario)) {
      statement_workspace_state(data_statement_import_workspace_status_v1(error_code="data_statement_import_workspace_input_invalid"));return()
    }
    tryCatch(
      {
        review<-statement_workspace_center$review_synthetic(scenario)
        statement_workspace_result(review)
        statement_workspace_state(data_statement_import_workspace_status_v1(review=review))
      },
      error=function(error) {
        code<-if(!is.null(error$code))as.character(error$code)else"data_statement_import_workspace_boundary_failed"
        statement_workspace_state(data_statement_import_workspace_status_v1(error_code=code))
      }
    )
  })

  shiny::observeEvent(input$portfolio_exchange_paths, safe(
    portfolio_exchange_service$paths(),
    function(model) {
      portfolio_exchange_paths_model(model)
      state(list(tone="neutral", title="Portfolio-Austauschordner angezeigt", copy="Der vollständige Pfad (lokal beim Eigentümer) ist nur in dieser Desktop-Sitzung sichtbar."))
    }
  ))
  shiny::observeEvent(input$portfolio_exchange_initialize, {
    if (!isTRUE(input$portfolio_exchange_initialize_confirm)) {
      state(list(tone="error", title="Austauschordner blockiert", copy=pl_error_text_v1("data_portfolio_csv_exchange_confirmation_required"))); return()
    }
    safe(portfolio_exchange_service$initialize(), function(model) {
      portfolio_exchange_paths_model(model); shiny::updateCheckboxInput(session,"portfolio_exchange_initialize_confirm",value=FALSE)
      state(list(tone="neutral", title="Portfolio-Austauschordner bereit", copy="Eingangsordner, Export und vorgemerkte Importe sind nur für den Eigentümer zugänglich angelegt; Bestand unverändert."))
    })
  })
  shiny::observeEvent(input$portfolio_exchange_export_prepare, safe(
    portfolio_exchange_service$export_prepare(),
    function(preview) {
      portfolio_exchange_export_model(preview); shiny::updateCheckboxInput(session,"portfolio_exchange_export_confirm",value=FALSE)
      state(list(tone="warning", title="Portfolio-Exportvorschau bereit", copy=paste(preview$record_count,"Datensätze ·",preview$asset_file_count,"Asset-Dateien ·",preview$account_file_count,"Konto-/Wallet-Dateien.")))
    }
  ))
  shiny::observeEvent(input$portfolio_exchange_export_execute, {
    if (is.null(portfolio_exchange_export_model()) || !isTRUE(input$portfolio_exchange_export_confirm)) {
      state(list(tone="error", title="Portfolio-Export blockiert", copy=pl_error_text_v1("data_portfolio_csv_exchange_confirmation_required"))); return()
    }
    safe(portfolio_exchange_service$export_execute(TRUE), function(result) {
      portfolio_exchange_export_model(result); shiny::updateCheckboxInput(session,"portfolio_exchange_export_confirm",value=FALSE)
      state(list(tone="neutral", title="Portfolio verlustfrei exportiert", copy=paste("Neu angelegtes Paket:",result$bundle_name,"· Bestand unverändert.")))
    })
  })
  shiny::observeEvent(input$portfolio_exchange_import_refresh, safe(
    portfolio_exchange_service$import_list(),
    function(model) {
      portfolio_exchange_import_list(model)
      choices <- if(!length(model$bundles)) c("Keine gültigen Pakete im Eingangsordner"="") else stats::setNames(vapply(model$bundles,`[[`,character(1L),"bundle_handle"),vapply(model$bundles,function(row)paste(row$record_count,"Datensätze ·",row$asset_count,"Assets ·",row$account_count,"Konten"),character(1L)))
      shiny::updateSelectInput(session,"portfolio_exchange_import_bundle",choices=choices,selected=if(length(model$bundles))model$bundles[[1L]]$bundle_handle else "")
      state(list(tone="neutral", title="Eingangsordner für Portfolios gelesen", copy=paste(length(model$bundles),"vollständig validierte Paket(e); kein Schreiben in den Bestand.")))
    }
  ))
  shiny::observeEvent(input$portfolio_exchange_import_prepare, {
    handle <- input$portfolio_exchange_import_bundle
    if(is.null(handle)||!nzchar(handle)){state(list(tone="error",title="Portfolio-Import blockiert",copy=pl_error_text_v1("data_portfolio_csv_exchange_preview_required")));return()}
    safe(portfolio_exchange_service$import_prepare(handle), function(preview) {
      portfolio_exchange_import_model(preview); shiny::updateCheckboxInput(session,"portfolio_exchange_import_confirm",value=FALSE)
      state(list(tone="warning", title="Portfolio-Importvorschau bereit", copy=paste(preview$record_count,"Datensätze · Redundanz",preview$redundancy_status,"· noch nichts in den Bestand geschrieben.")))
    })
  })
  shiny::observeEvent(input$portfolio_exchange_import_execute, {
    if(is.null(portfolio_exchange_import_model())||!isTRUE(input$portfolio_exchange_import_confirm)){state(list(tone="error",title="Portfolio-Import blockiert",copy=pl_error_text_v1("data_portfolio_csv_exchange_confirmation_required")));return()}
    safe(portfolio_exchange_service$import_execute(TRUE), function(result) {
      portfolio_exchange_import_model(result); shiny::updateCheckboxInput(session,"portfolio_exchange_import_confirm",value=FALSE);try(refresh_portfolio_exchange_staged(),silent=TRUE)
      state(list(tone="warning", title="Portfolio-Paket verlustfrei in den Eingangsordner übernommen", copy="Katalog, gekoppelte Transaktionen, Buchungen und Cash warten auf getrennte Übergaben je Bereich; keine doppelten Fakten erzeugt."))
    })
  })
  shiny::observeEvent(input$portfolio_exchange_staged_refresh,safe(refresh_portfolio_exchange_staged(),function(model){state(list(tone="neutral",title="Vorgemerkte Portfolio-Pakete gelesen",copy=paste(length(model$imports),"Paket(e) mit getrenntem Stand je Bereich.")))}))
  shiny::observeEvent(input$portfolio_exchange_handoff_prepare,{
    staged<-input$portfolio_exchange_staged_import;domain<-input$portfolio_exchange_handoff_domain
    if(is.null(staged)||!nzchar(staged)||is.null(domain)||!nzchar(domain)){state(list(tone="error",title="Übergabe je Bereich blockiert",copy=pl_error_text_v1("data_portfolio_csv_exchange_preview_required")));return()}
    safe(portfolio_exchange_service$handoff_prepare(domain,staged),function(preview){portfolio_exchange_handoff_model(preview);shiny::updateCheckboxInput(session,"portfolio_exchange_handoff_confirm",value=FALSE);state(list(tone="warning",title="Getrennte Vorschau je Bereich bereit",copy=paste(preview$source_record_count,"Quelldatensätze ·",preview$create_count,"neue Wirkungen ·",preview$reuse_count,"Wiederverwendungen · noch keine Wirkung.")))})
  })
  shiny::observeEvent(input$portfolio_exchange_handoff_execute,{
    preview<-portfolio_exchange_handoff_model();domain<-input$portfolio_exchange_handoff_domain
    if(is.null(preview)||!isTRUE(input$portfolio_exchange_handoff_confirm)||!identical(preview$domain,domain)){state(list(tone="error",title="Übergabe je Bereich blockiert",copy=pl_error_text_v1("data_portfolio_csv_exchange_confirmation_required")));return()}
    safe(portfolio_exchange_service$handoff_execute(domain,TRUE),function(result){portfolio_exchange_handoff_model(result);shiny::updateCheckboxInput(session,"portfolio_exchange_handoff_confirm",value=FALSE);try(refresh_portfolio_exchange_staged(),silent=TRUE);state(list(tone=if(isTRUE(result$candidate_only))"warning"else"neutral",title="Getrennte Übergabe je Bereich abgeschlossen",copy=if(isTRUE(result$candidate_only))paste(result$created_count,"Vorschläge bereit; die fachliche Bestätigung von Cash und Buchungen bleibt getrennt.")else paste(result$created_count,"Wirkungen in den Stammdaten · Beleg",result$receipt_ref)))})
  })
  shiny::observeEvent(input$portfolio_exchange_recovery_refresh,safe(portfolio_exchange_service$handoff_recovery_candidates(),function(model){portfolio_exchange_recovery_list(model);choices<-if(!length(model$candidates))c("Keine unterbrochenen Übergaben"="")else stats::setNames(vapply(model$candidates,`[[`,character(1L),"recovery_ref"),vapply(model$candidates,function(item)paste(item$domain,"·",item$staged_import_handle,"·",item$attempted_at_utc),character(1L)));shiny::updateSelectInput(session,"portfolio_exchange_recovery_candidate",choices=choices,selected=if(length(model$candidates))model$candidates[[1L]]$recovery_ref else "");state(list(tone=if(length(model$candidates))"warning"else"neutral",title="Unterbrochene Übergaben gelesen",copy=paste(length(model$candidates),"unterbrochene, noch nicht wiederholte Versuche.")))}))
  shiny::observeEvent(input$portfolio_exchange_recovery_prepare,{
    ref<-input$portfolio_exchange_recovery_candidate;if(is.null(ref)||!nzchar(ref)){state(list(tone="error",title="Wiederaufnahme der Übergabe blockiert",copy=pl_error_text_v1("portfolio_csv_handoff_recovery_missing")));return()}
    safe(portfolio_exchange_service$handoff_recovery_prepare(ref),function(preview){portfolio_exchange_recovery_model(preview);shiny::updateCheckboxInput(session,"portfolio_exchange_recovery_confirm",value=FALSE);state(list(tone="warning",title="Vorschau der Wiederaufnahme bereit",copy=paste("Bereich",preview$domain,"· Wirkung",preview$effect_state,"· kein blinder neuer Versuch.")))})
  })
  shiny::observeEvent(input$portfolio_exchange_recovery_execute,{
    if(is.null(portfolio_exchange_recovery_model())||!isTRUE(input$portfolio_exchange_recovery_confirm)){state(list(tone="error",title="Wiederaufnahme der Übergabe blockiert",copy=pl_error_text_v1("data_portfolio_csv_exchange_confirmation_required")));return()}
    safe(portfolio_exchange_service$handoff_recovery_execute(TRUE),function(result){portfolio_exchange_recovery_model(result);shiny::updateCheckboxInput(session,"portfolio_exchange_recovery_confirm",value=FALSE);try(refresh_portfolio_exchange_staged(),silent=TRUE);state(list(tone="neutral",title="Wiederaufnahme der Übergabe abgeschlossen",copy=paste("Bereich",result$domain,"· Status",result$status,"· Beleg",result$receipt_ref)))})
  })
  shiny::observeEvent(input$portfolio_exchange_cash_refresh,{
    staged<-input$portfolio_exchange_staged_import;if(is.null(staged)||!nzchar(staged)){state(list(tone="error",title="Cash-Vorschläge blockiert",copy=pl_error_text_v1("data_portfolio_csv_exchange_preview_required")));return()}
    safe(portfolio_exchange_service$cash_candidates(staged),function(model){portfolio_exchange_cash_list(model);choices<-if(!length(model$candidates))c("Keine Cash-Vorschläge"="")else stats::setNames(vapply(model$candidates,`[[`,character(1L),"candidate_ref"),vapply(model$candidates,function(item)paste(item$action_type,"·",item$status),character(1L)));ready<-Filter(function(item)identical(item$status,"ready_for_cash_review"),model$candidates);shiny::updateSelectInput(session,"portfolio_exchange_cash_candidate",choices=choices,selected=if(length(ready))ready[[1L]]$candidate_ref else "");state(list(tone=if(length(ready))"warning"else"neutral",title="Cash-Vorschläge des Portfolios gelesen",copy=paste(length(ready),"Vorschläge bereit für die gemeinsame Cash-Prüfung.")))})
  })
  shiny::observeEvent(input$portfolio_exchange_cash_review,{
    staged<-input$portfolio_exchange_staged_import;candidate<-input$portfolio_exchange_cash_candidate
    if(is.null(staged)||!nzchar(staged)||is.null(candidate)||!nzchar(candidate)){state(list(tone="error",title="Cash-Prüfung blockiert",copy=pl_error_text_v1("portfolio_csv_handoff_cash_candidate_invalid")));return()}
    safe({resolved<-portfolio_exchange_service$cash_candidate(staged,candidate);preview<-data_cash_coverage_editor_prepare_reviewed_v1(cash_editor,runtime$context,resolved$trusted_candidate,now_utc());list(public=resolved$public_candidate,preview=preview)},function(result){portfolio_exchange_cash_model(result$public);cash_preview(result$preview);shiny::updateCheckboxInput(session,"cash_confirm",value=FALSE);state(list(tone="warning",title="Portfolio-Candidate in Cash-Vorschau",copy="Die gemeinsame Übergabe an Cash bewahrt die Herkunft (Code: reviewed_import); erst die eigene Cash-Bestätigung schreibt in den Cash-Bestand (Schema 2901)."))})
  })

  shiny::observeEvent(input$initialize_data_space, {
    if (!isTRUE(input$confirm_initialize)) {
      state(list(tone = "error", title = "Initialisierung blockiert", copy = pl_error_text_v1("desktop_product_data_space_confirmation_required")))
      return()
    }
    safe(
      spotcore::desktop_product_initialize_data_space_v1(runtime, file.path(project_root, "contracts"), now_utc(), "INITIALIZE_EMPTY_DATA_SPACE"),
      function(result) {
        shiny::updateCheckboxInput(session, "confirm_initialize", value = FALSE)
        need_setup(FALSE)
        state(list(tone = "neutral", title = "Portelyra eingerichtet", copy = "Es wurden noch keine fachlichen Datensätze angelegt."))
        invisible(read_workspace())
      }
    )
  })

  shiny::observeEvent(input$read_workspace, safe(read_workspace(), function(value) invisible(value)))
  # Die Uebersicht in den Stammdaten liest beim Aufklappen, ohne die Rueckmeldung der letzten Aktion zu ueberschreiben.
  shiny::observeEvent(input$data_workspace_overview_open, {
    if (isTRUE(input$data_workspace_overview_open)) tryCatch(workspace(spotcore::desktop_product_workspace_v1(runtime)), error = function(error) NULL)
  }, ignoreInit = TRUE)

  # Der Asset-Katalog wurde bisher nur auf Klick geladen: ohne "Asset-Center
  # aktualisieren" blieben Assetliste, Zuordnungen und Bewertungszeitraum leer.
  # Wie beim Cash-Katalog laedt er jetzt beim Start und beim Wechsel in die
  # Stammdaten- und Marktdaten-Tabs (#283, 21.09.2026).
  # Beim Reiterwechsel wird der Asset-Katalog neu gelesen, die Activity-Sicht aber
  # nur, wenn noch keine da ist: Ein Reiterwechsel aendert nichts auf der Platte,
  # und jeder Schreibvorgang liest die Sicht danach selbst neu. Das volle Lesen
  # kostete je Wechsel rund zweieinhalb Sekunden.
  asset_center_autoload <- function(reuse = FALSE) {
    tryCatch({
      asset_center_refresh(shiny::isolate(input$asset_center_asset))
      refresh_activity_catalog(reuse = reuse)
    }, error = function(error) invisible(NULL))
  }
  shiny::observeEvent(TRUE, asset_center_autoload(), once = TRUE)
  shiny::observeEvent(input$asset_center_step, {
    if (input$asset_center_step %in% c("1 · Stammdaten", "Marktdaten")) asset_center_autoload(reuse = TRUE)
    if (identical(input$asset_center_step, "transactions") && !identical(canonical_stamp(), activity_catalog_stamp))
      tryCatch(refresh_activity_catalog(), error = function(error) invisible(NULL))
  }, ignoreInit = TRUE)
  # Eine Auswahl in der Suche fuehrt den ganzen Arbeitskontext: Buchungstabelle,
  # Formularziel und Asset-Stand. Bis rc.225 wurde `asset_center_selected_ref`
  # nur innerhalb von asset_center_refresh() nachgezogen - wer in der Suche
  # umschaltete, bekam eine Tabelle mit den Buchungen des neuen Assets und ein
  # Formular, das noch auf dem alten stand. Dieses Auseinanderlaufen ist der
  # Fehler, der zweimal eine Buchung unsichtbar gemacht hat (#424).
  shiny::observeEvent(input$asset_center_asset, {
    gewaehlt <- input$asset_center_asset
    gewaehlt <- if (is.character(gewaehlt) && length(gewaehlt) == 1L && !is.na(gewaehlt)) gewaehlt else ""
    if (identical(gewaehlt, asset_center_selected_ref)) return(invisible(NULL))
    asset_center_selected_ref <<- gewaehlt
    tryCatch(refresh_activity_catalog(reuse = TRUE), error = function(error) invisible(NULL))
  }, ignoreInit = TRUE, ignoreNULL = FALSE)
  # Der Asset-Filter grenzt allein die Suche ein. Die Auswahl bleibt, wo sie ist:
  # Ein Asset ausserhalb des Filters bleibt gewaehlt und in der Liste.
  shiny::observeEvent(list(input$asset_center_filter_holding, input$asset_center_filter_accounts, input$asset_center_filter_types), {
    asset_center_filter <<- data_asset_center_filter_input_v1(
      input$asset_center_filter_holding, input$asset_center_filter_accounts, input$asset_center_filter_types)
    core <- asset_center_catalog()
    if (!is.null(core)) invisible(asset_center_send_choices(core, input$asset_center_asset))
  }, ignoreInit = TRUE, ignoreNULL = FALSE)
  # Der Filter rechnet auf der Buchungssicht: Erst mit ihr lassen sich die Konten
  # zuordnen, und nach einer Buchung kann ein Asset hinzukommen oder herausfallen.
  # Als Beobachter und nicht im Lesen selbst: Nach einem Schreibvorgang wird die
  # Sicht zweimal gesetzt, erst mit veraltetem, dann mit fortgeschriebenem
  # FIFO-Stand - gerechnet wird einmal, auf dem Stand am Ende des Durchlaufs.
  #
  # Ohne ignoreInit: Beim Sitzungsstart liest ein frueher angelegter Beobachter
  # die Sicht im selben Durchlauf, in dem dieser zum ersten Mal laeuft. Mit
  # ignoreInit galt das als Anfangszustand, und die Kontenliste blieb leer
  # (im Browser, testServer zeigte es nicht).
  shiny::observeEvent(list(activity_read_view(), activity_catalog()), {
    asset_center_filter_sync_options()
    core <- asset_center_catalog()
    if (data_asset_center_filter_active_v1(asset_center_filter) && !is.null(core))
      invisible(asset_center_send_choices(core, input$asset_center_asset))
  }, ignoreNULL = FALSE)
  shiny::observeEvent(input$asset_center_filter_reset, {
    shiny::updateSelectInput(session, "asset_center_filter_holding", selected = "any")
    shiny::updateSelectizeInput(session, "asset_center_filter_accounts", selected = character())
    shiny::updateSelectizeInput(session, "asset_center_filter_types", selected = character())
  }, ignoreInit = TRUE)
  output$asset_center_filter_state <- shiny::renderUI({
    state <- asset_center_filter_status()
    text <- if (is.null(state)) NULL else data_asset_center_filter_text_v1(state)
    if (is.null(text)) NULL
    else if (identical(text$tone, "warning")) portelyra_status_panel("Asset-Filter", text$copy, tone = "warning")
    else shiny::p(class = "pl-section-copy", text$copy)
  })
  shiny::observeEvent(input$asset_center_refresh, safe({
    asset_center_refresh()
    refresh_activity_catalog()
    refresh_activity_corrections()
  }, function(value) {
    asset_center_market_coverage(NULL);asset_center_fx_coverage(NULL);asset_center_calendar_gaps(NULL);asset_center_completion_plan(NULL);asset_center_completion_batch(NULL)
    state(list(tone = "neutral", title = "Asset-Center aktualisiert", copy = "Stammdaten, Kurszuordnungen sowie Transaktionsauswahl und Historie wurden ohne Kursabruf gelesen. Keine Buchung oder Berechnung."))
  }))
  shiny::observeEvent(list(input$asset_center_coverage_start,input$asset_center_coverage_end,input$asset_center_completion_currency),{
    asset_center_market_coverage(NULL);asset_center_fx_coverage(NULL);asset_center_calendar_gaps(NULL);asset_center_completion_plan(NULL);asset_center_completion_batch(NULL)
  },ignoreInit=TRUE)
  # Cash keeps amounts in currency units; two decimals are the usual precision.
  shiny::observeEvent(input$asset_center_domain, {
    shiny::updateSelectInput(session, "asset_center_scale", selected = if (identical(input$asset_center_domain, "cash")) "2" else "8")
  }, ignoreInit = TRUE)
  shiny::observeEvent(list(input$asset_center_mode, input$asset_center_domain, input$asset_center_name, input$asset_center_isin,
    input$asset_center_currency, input$asset_center_type, input$asset_center_scale, input$asset_center_valuation), {
    asset_center_core_preview(NULL); shiny::updateCheckboxInput(session, "asset_center_core_confirm", value = FALSE)
  }, ignoreInit = TRUE, priority = 100)
  shiny::observeEvent(input$asset_center_core_prepare, {
    if (!is.character(input$asset_center_domain) || !input$asset_center_domain %in% c("cash", "non_cash")) {
      state(list(tone = "warning", title = "Art des Assets wählen", copy = "Bitte zuerst entscheiden: Cash oder Wertpapier/Krypto/Fonds. Die Entscheidung bestimmt Ertragsarten, FIFO und Bewertung.")); return()
    }
    # Fehlt die Kurswaehrung, sagt das die Karte selbst statt "Aktion blockiert" mit Sammelcode (#447).
    currency_text <- toupper(trimws(if (is.null(input$asset_center_currency)) "" else input$asset_center_currency))
    if (!grepl("^[A-Z]{3}$", currency_text)) {
      state(list(tone = "warning", title = "Kurswährung fehlt", copy = "Bitte die Kurswährung als dreistelligen Code eintragen, z. B. EUR. Die Suche beim Kursanbieter liefert sie nicht immer mit.")); return()
    }
    # One Cash asset per currency: Cash accounts, not assets, separate the balances (#184).
    if (identical(input$asset_center_domain, "cash")) {
      currency <- toupper(trimws(if (is.null(input$asset_center_currency)) "" else input$asset_center_currency))
      existing <- data_asset_center_cash_duplicate_v1(asset_center_catalog(), currency)
      if (!is.null(existing)) {
        state(list(tone = "warning", title = sprintf("Für %s gibt es bereits ein Cash-Asset", currency),
          copy = sprintf("„%s“ ist schon angelegt. Cash wird über Konten unterschieden: bitte stattdessen ein weiteres Konto anlegen.", existing$display_name))); return()
      }
    }
    asset_center_core_prepare_run()
  })
  asset_center_core_prepare_run <- function() safe({
    if (!identical(input$asset_center_mode, "new")) stop("desktop_catalog_preview_required", call. = FALSE)
    desktop_catalog_editor_prepare_v1(asset_center_catalog_editor, runtime$context, asset_center_core_form(), now_utc()) },
    function(preview) {
      asset_center_core_preview(preview); shiny::updateCheckboxInput(session, "asset_center_core_confirm", value = FALSE)
      state(list(tone = "neutral", title = "Stammdaten geprüft", copy = "Noch wurde kein Asset angelegt."))
    }
  )
  shiny::observeEvent(input$asset_center_core_execute, {
    preview <- asset_center_core_preview()
    if (is.null(preview)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("desktop_catalog_preview_required"))); return()
    }
    before <- asset_center_catalog(); before_refs <- if (is.null(before)) character() else vapply(before$assets, `[[`, character(1L), "ref")
    before_names <- if (is.null(before)) character() else vapply(before$assets, function(row) as.character(row$display_name), character(1L))
    name <- trimws(shiny::isolate(input$asset_center_name))
    safe(
      desktop_catalog_editor_execute_v1(asset_center_catalog_editor, runtime$context, preview, isTRUE(input$asset_center_core_confirm)),
      function(result) {
        model <- asset_center_refresh(""); new_refs <- setdiff(vapply(model$assets, `[[`, character(1L), "ref"), before_refs)
        # Die Referenzen der Liste sind Positionen in der sortierten Liste: Landet das neue Asset alphabetisch davor, verschieben
        # sie sich, und "neu" waere ein anderes (#455, im Test gefunden 22.10.2026). Eindeutig ist der Name, den es vorher nicht gab.
        created <- if (!name %in% before_names) Filter(function(row) identical(row$display_name, name), model$assets) else list()
        selected <- if (length(created) == 1L) created[[1L]]$ref else if (length(new_refs) == 1L) new_refs[[1L]] else input$asset_center_asset
        shiny::updateRadioButtons(session, "asset_center_mode", selected = "existing")
        asset_center_select(selected)
        asset_center_core_preview(NULL); shiny::updateCheckboxInput(session, "asset_center_core_confirm", value = FALSE)
        invisible(tryCatch(cash_import_load(), error = function(error) NULL))
        state(list(tone = "positive", title = "Asset angelegt", copy = "Das neue Asset ist ausgewählt. Optional Konto / Wallet wählen und „Dieses Asset in neuer Transaktion verwenden“. Kursanbieter und Steuer bleiben getrennt bestätigt."))
        invisible(read_workspace())
        # Nach dem Anlegen gleich weiter (#455) - ausser es ging aus einem Import heraus; dann geht es dorthin zurueck.
        if (is.null(securities_import_return()) && length(created) == 1L)
          asset_center_created(list(ref = created[[1L]]$ref, name = created[[1L]]$display_name, type = created[[1L]]$asset_type))
        securities_import_return_after_create(if (length(created) == 1L) list(ref = created[[1L]]$ref, name = created[[1L]]$display_name, type = created[[1L]]$asset_type,
                                                                              valuation = created[[1L]]$valuation_method))
      }
    )
  })
  # ETF <-> Fonds (#447, rc.274): pruefen, bestaetigen, wechseln - wie die Preiswaehrung.
  asset_center_fund_type_preview <- shiny::reactiveVal(NULL)
  asset_center_fund_type_notice <- shiny::reactiveVal(NULL)   # gilt nur fuer das Asset, an dem gewechselt wurde
  output$asset_center_fund_type_ui <- shiny::renderUI(data_asset_center_fund_type_ui_v1(asset_center_selected()))
  output$asset_center_fund_type_notice <- shiny::renderUI({
    notice <- asset_center_fund_type_notice()
    same <- is.list(notice) && identical(notice$asset_id, tryCatch(asset_center_selected_id(), error = function(error) NULL))
    if (same) portelyra_status_panel(notice$title, notice$copy, tone = notice$tone)
  })
  shiny::observeEvent(input$asset_center_asset, asset_center_fund_type_preview(NULL), ignoreInit = TRUE)
  shiny::observeEvent(input$asset_center_fund_type_prepare, safe(
    desktop_catalog_editor_prepare_v1(asset_center_catalog_editor, runtime$context, asset_center_fund_type_form(), now_utc()),
    function(preview) {
      asset_center_fund_type_preview(preview)
      shiny::updateCheckboxInput(session, "asset_center_fund_type_confirm", value = FALSE)
      label <- function(type) if (identical(type, "etf")) "ETF" else "Fonds"
      checked <- list(tone = "warning", title = "Wechsel der Fondsart geprüft", copy = paste(label(preview$current_asset_type), "→",
        label(preview$proposed_asset_type), "· Buchungen, Konten, Kurse und Kursfreigabe bleiben; danach gilt die Steuervorgabe des neuen Typs."))
      state(checked); asset_center_fund_type_notice(c(checked, list(asset_id = asset_center_selected_id())))
    }))
  shiny::observeEvent(input$asset_center_fund_type_execute, {
    preview <- asset_center_fund_type_preview()
    if (is.null(preview) || !isTRUE(input$asset_center_fund_type_confirm)) {
      state(list(tone = "error", title = "Wechsel der Fondsart blockiert", copy = "Erst prüfen und genau diesen Wechsel bestätigen.")); return()
    }
    changed_id <- asset_center_selected_id()
    safe(desktop_catalog_editor_execute_v1(asset_center_catalog_editor, runtime$context, preview, TRUE), function(result) {
      asset_center_refresh(input$asset_center_asset)
      asset_center_fund_type_preview(NULL)
      shiny::updateCheckboxInput(session, "asset_center_fund_type_confirm", value = FALSE)
      # Erst neu lesen: read_workspace() setzt selbst "Daten gelesen" und ueberschriebe die Meldung (im Browser gemessen).
      invisible(read_workspace())
      done <- list(tone = "positive", title = "Fondsart gewechselt",
        copy = "Fassung auditiert · Buchungen, Konten, Kurse und Kursfreigabe unverändert. Im Reiter „Steuer“ „Einstellungen lesen“, damit die Vorgabe des neuen Typs gilt.")
      state(done); asset_center_fund_type_notice(c(done, list(asset_id = changed_id)))
    })
  })
  shiny::observeEvent(input$asset_center_price_currency_prepare, safe(
    desktop_catalog_editor_prepare_v1(
      asset_center_catalog_editor, runtime$context, asset_center_price_currency_form(), now_utc()
    ),
    function(preview) {
      asset_center_price_currency_preview(preview)
      shiny::updateCheckboxInput(session, "asset_center_price_currency_confirm", value = FALSE)
      state(list(
        tone = "warning", title = "Preiswährungs-Korrektur geprüft",
        copy = paste(
          preview$current_price_currency, "→", preview$proposed_price_currency,
          "· keine FX-Umrechnung · Kurszuordnung und Buchungen unverändert."
        )
      ))
    }
  ))
  shiny::observeEvent(input$asset_center_price_currency_execute, {
    preview <- asset_center_price_currency_preview()
    if (is.null(preview) || !isTRUE(input$asset_center_price_currency_confirm)) {
      state(list(
        tone = "error", title = "Preiswährungs-Korrektur blockiert",
        copy = pl_error_text_v1("desktop_catalog_confirmation_required")
      ))
      return()
    }
    safe(
      desktop_catalog_editor_execute_v1(
        asset_center_catalog_editor, runtime$context, preview, TRUE
      ),
      function(result) {
        selected_ref <- input$asset_center_asset
        model <- asset_center_refresh(selected_ref)
        selected <- tryCatch(
          data_asset_center_selected_v1(model, selected_ref), error = function(error) NULL
        )
        if (!is.null(selected)) {
          shiny::updateTextInput(
            session, "asset_center_price_currency_target", value = selected$price_currency
          )
        }
        asset_center_price_currency_preview(NULL)
        shiny::updateCheckboxInput(session, "asset_center_price_currency_confirm", value = FALSE)
        invisible(read_workspace())   # vor der Meldung, sonst steht "Daten gelesen" da
        state(list(
          tone = "positive", title = "Fachliche Preiswährung korrigiert",
          copy = "Fassung auditiert (nur fortgeschrieben) · keine FX-Umrechnung · Kurszuordnung und Buchungen unverändert."
        ))
      }
    )
  })
  # Inline portfolio and account maintenance (#363, #365). One preview binds the
  # command; "Geprüft speichern" executes exactly that preview. Any form change
  # discards the preview, so a stale check can never be written.
  # Konten (#425/#426, 14.10.2026): Das Konto zum Umbenennen wird im Formular gewaehlt; ein Institut laesst sich fuer alle
  # seine Konten umbenennen; die Kontonummer steht im selben Formular und wird neben den Stammdaten gespeichert.
  asset_center_inline_preview <- list(account = shiny::reactiveVal(NULL), portfolio = shiny::reactiveVal(NULL))
  # Rueckmeldung am Formular selbst: geprueft, gespeichert oder der Grund, warum nicht.
  asset_center_inline_notice <- list(account = shiny::reactiveVal(NULL), portfolio = shiny::reactiveVal(NULL))
  # Die Auswahl im Formular ist eine Position in der Kontenliste; sie verschiebt sich, wenn ein Konto hinzukommt.
  # Festgehalten wird deshalb die Kennung des gewaehlten Kontos - sie bleibt im Prozess.
  asset_center_account_target_id <- NULL
  asset_center_account_id <- function(ref) {
    if (!is.character(ref) || length(ref) != 1L || is.na(ref) || !nzchar(ref)) return(NULL)
    tryCatch(desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "account", ref), error = function(error) NULL)
  }
  asset_center_account_ref_of <- function(id) {
    model <- asset_center_catalog(); if (is.null(id) || is.null(model)) return("")
    hit <- Filter(function(row) identical(asset_center_account_id(row$ref), id), model$accounts)
    if (length(hit) == 1L) hit[[1L]]$ref else ""
  }
  asset_center_accounts <- function() { model <- asset_center_catalog(); if (is.null(model)) list() else model$accounts }
  asset_center_account_number_of <- function(id) {
    if (is.null(id) || is.null(account_reference_service)) return(NULL)
    references <- tryCatch(account_reference_service$read()$references, error = function(error) NULL)
    if (is.list(references) && is.list(references[[id]])) data_account_reference_text_v1(references[[id]]$account_number) else NULL
  }
  asset_center_inline_target <- function(kind) {
    value <- if (identical(kind, "account")) input$asset_center_account_target else input$asset_center_portfolio_target
    # #547: Das Formular in den Einstellungen waehlt selbst; ohne Wahl gilt wie bisher die Auswahl der Kopfzeile.
    if (identical(kind, "portfolio") && (!is.character(value) || !nzchar(value))) value <- input$asset_center_portfolio
    if (identical(kind, "portfolio") && (!is.character(value) || !nzchar(value))) value <- asset_center_selected_portfolio_ref
    if (is.character(value) && length(value) == 1L && !is.na(value)) value else ""
  }
  asset_center_inline_row <- function(kind, ref) {
    model <- asset_center_catalog(); if (is.null(model) || !nzchar(ref)) return(NULL)
    matched <- Filter(function(row) identical(row$ref, ref), model[[paste0(kind, "s")]])
    if (length(matched) == 1L) matched[[1L]] else NULL
  }
  asset_center_inline_form <- function(kind) {
    action <- input[[paste0("asset_center_", kind, "_action")]]
    account <- identical(kind, "account")
    list(
      action = action, entity_type = kind,
      entity_ref = if (identical(action, "update")) asset_center_inline_target(kind) else "",
      portfolio_ref = if (account && identical(action, "create")) { value <- input$asset_center_portfolio
        if (!is.character(value) || !nzchar(value)) value <- asset_center_selected_portfolio_ref
        if (is.character(value) && length(value) == 1L && !is.na(value)) value else "" } else "",
      display_name = trimws(if (is.null(input[[paste0("asset_center_", kind, "_name")]])) "" else input[[paste0("asset_center_", kind, "_name")]]),
      base_currency = if (account) "EUR" else toupper(trimws(input$asset_center_portfolio_currency)),
      account_type = if (account) input$asset_center_account_type else "securities",
      institution_label = if (account) data_asset_center_institution_value_v1(input$asset_center_account_institution, asset_center_accounts()) else "",
      asset_type = "other", price_currency = "EUR", quantity_scale = "0", valuation_method = "transaction_only", isin = ""
    )
  }
  asset_center_inline_blocker <- function(kind, form) {
    if (identical(form$action, "update") && !nzchar(form$entity_ref)) {
      return(if (identical(kind, "account")) "Bitte im Formular das Konto wählen, das umbenannt werden soll." else "Bitte im Formular das Portfolio wählen, das umbenannt werden soll.")
    }
    if (identical(kind, "account") && identical(form$action, "create") && !nzchar(form$portfolio_ref)) return("Bitte zuerst oben ein Portfolio auswählen.")
    if (!nzchar(form$display_name)) return("Bitte eine Bezeichnung eingeben.")
    # Fuer die Beta nur Euro (Endabnahme 19.11.2026): auch ein Aufruf am Formular vorbei legt kein Portfolio in anderer Waehrung an.
    if (identical(kind, "portfolio") && identical(form$action, "create") && !identical(form$base_currency, "EUR"))
      return("Portfolios führt Portelyra vorerst nur in Euro; weitere Währungen kommen später.")
    NULL
  }
  asset_center_account_type_label <- c(securities = "Wertpapierdepot", crypto_wallet = "Krypto-Wallet / -Depot", bank = "Bankkonto", cash = "Cash",
    external = "Extern", other = "Sonstiges")
  for (inline_kind in c("account", "portfolio")) local({
    kind <- inline_kind; account <- identical(kind, "account")
    label <- if (account) "Konto / Wallet" else "Portfolio"
    preview_value <- asset_center_inline_preview[[kind]]
    notice_value <- asset_center_inline_notice[[kind]]
    written_at <- NULL
    # Was `safe` als Fehler in die Statuszeile schreibt, steht auch am Formular.
    notice_failure <- function(title) {
      current <- shiny::isolate(state())
      notice_value(list(tone = "error", title = title, copy = if (is.list(current) && is.character(current$copy)) current$copy else ""))
    }
    notice_error <- function(title, copy) { preview_value(NULL); state(list(tone = "error", title = title, copy = copy)); notice_value(list(tone = "error", title = title, copy = copy)) }
    checked_notice <- function() {
      state(list(tone = "warning", title = paste(label, "geprüft"), copy = "Mit „Geprüft speichern“ wird genau diese Änderung geschrieben."))
      notice_value(list(tone = "warning", title = paste(label, "geprüft – noch nicht gespeichert"),
        copy = "Mit „Geprüft speichern“ wird genau die Änderung der Tabelle unten geschrieben."))
    }
    as_table <- function(rows) data.frame(Feld = vapply(rows, `[[`, character(1L), 1L), Wert = vapply(rows, `[[`, character(1L), 2L), check.names = FALSE)
    output[[paste0("asset_center_", kind, "_notice")]] <- shiny::renderUI({
      current <- notice_value()
      if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone)
    })
    watched <- if (account) {
      c("asset_center_account_action", "asset_center_account_name", "asset_center_account_type", "asset_center_account_institution", "asset_center_account_target",
        "asset_center_account_number", "asset_center_institution_target", "asset_center_institution_name", "asset_center_portfolio")
    } else c("asset_center_portfolio_action", "asset_center_portfolio_name", "asset_center_portfolio_currency", "asset_center_portfolio",
             "asset_center_portfolio_target")
    shiny::observeEvent(lapply(watched, function(id) input[[id]]), {
      preview_value(NULL)
      # Nach dem Speichern leert die App das Namensfeld und waehlt das neue Konto - das ist keine Eingabe; die Meldung bleibt.
      if (is.null(written_at) || as.numeric(difftime(Sys.time(), written_at, units = "secs")) > 3) notice_value(NULL)
    }, ignoreInit = TRUE)
    # Renaming starts from the current values so optional fields are not cleared by accident.
    shiny::observeEvent(list(input[[paste0("asset_center_", kind, "_action")]], if (account) input$asset_center_account_target else
                             list(input$asset_center_portfolio, input$asset_center_portfolio_target)), {
      if (!identical(input[[paste0("asset_center_", kind, "_action")]], "update")) return()
      row <- asset_center_inline_row(kind, asset_center_inline_target(kind)); if (is.null(row)) return()
      shiny::updateTextInput(session, paste0("asset_center_", kind, "_name"), value = row$display_name)
      if (account) {
        shiny::updateSelectizeInput(session, "asset_center_account_institution", selected = if (is.null(row$institution_label)) "" else row$institution_label)
        number <- asset_center_account_number_of(asset_center_account_id(row$ref))
        shiny::updateTextInput(session, "asset_center_account_number", value = if (is.null(number)) "" else number)
      }
    }, ignoreInit = TRUE)
    # Konto anlegen: Die Felder beginnen leer, auch wenn eben ein Konto zum Umbenennen gewaehlt war.
    if (account) shiny::observeEvent(input$asset_center_account_action, {
      if (identical(input$asset_center_account_action, "create")) {
        shiny::updateTextInput(session, "asset_center_account_name", value = "")
        shiny::updateSelectizeInput(session, "asset_center_account_institution", selected = "")
        shiny::updateTextInput(session, "asset_center_account_number", value = "")
      }
      # Wer umbenennt, ohne im Formular gewaehlt zu haben, beginnt beim Konto der Transaktionsmaske.
      if (identical(input$asset_center_account_action, "update") && !nzchar(asset_center_inline_target("account"))) {
        custody <- input$asset_center_custody_account
        if (is.character(custody) && length(custody) == 1L && nzchar(custody)) shiny::updateSelectInput(session, "asset_center_account_target", selected = custody)
      }
    }, ignoreInit = TRUE)
    # Ein Institut fuer alle seine Konten umbenennen: je Konto ein Katalogschritt, geprueft wird der ganze Vorgang.
    institution_prepare <- function() {
      old <- input$asset_center_institution_target
      if (!is.character(old) || length(old) != 1L || is.na(old) || !nzchar(old)) return(notice_error("Institut nicht geprüft", "Bitte das Institut wählen, das umbenannt werden soll."))
      accounts <- asset_center_accounts()
      renamed <- data_asset_center_institution_rename_v1(old, input$asset_center_institution_name, accounts)
      if (!nzchar(renamed$name)) return(notice_error("Institut nicht geprüft", "Bitte den neuen Namen des Instituts eingeben."))
      if (identical(renamed$name, old)) return(notice_error("Institut nicht geprüft", "Der neue Name gleicht dem bisherigen."))
      members <- Filter(function(row) !identical(row$status, "archived") && is.character(row$institution_label) && identical(trimws(row$institution_label), old), accounts)
      if (!length(members)) return(notice_error("Institut nicht geprüft", "Zu diesem Institut gibt es kein aktives Konto mehr. Bitte oben „Stammdaten neu lesen“."))
      ids <- vapply(members, function(row) { id <- asset_center_account_id(row$ref); if (is.null(id)) "" else id }, character(1L))
      if (!all(nzchar(ids))) return(notice_error("Institut nicht geprüft", "Die Stammdaten ließen sich nicht lesen. Bitte oben „Stammdaten neu lesen“."))
      names <- sort(vapply(members, function(row) as.character(row$display_name), character(1L)))
      rows <- list(c("Vorgang", "Institut umbenennen"), c("Bisheriger Name", old), c("Neuer Name", renamed$name),
        c("Konten", sprintf("%d: %s", length(members), paste(names, collapse = " · "))))
      if (isTRUE(renamed$merge)) rows <- c(rows, list(c("Hinweis", sprintf("„%s“ gibt es schon – die Konten kommen zu diesem Institut.", renamed$name))))
      rows <- c(rows, list(c("Wirkung", "Nur die Angabe „Institut / Börse“ an diesen Konten ändert sich; Buchungen und Bestände bleiben. Je Konto eine neue Fassung.")))
      preview_value(list(kind = "institution", old = old, name = renamed$name, ids = sort(ids), table = as_table(rows)))
      checked_notice()
    }
    institution_execute <- function(preview) {
      done <- 0L; failure <- NULL
      tryCatch({
        desktop_catalog_editor_refresh_v1(asset_center_catalog_editor, runtime$context)
        current <- Filter(function(row) !identical(row$status, "archived") && is.character(row$institution_label) && identical(trimws(row$institution_label), preview$old),
          asset_center_catalog_editor$catalog$public$accounts)
        current_ids <- sort(vapply(current, function(row) { id <- asset_center_account_id(row$ref); if (is.null(id)) "" else id }, character(1L)))
        if (!identical(current_ids, preview$ids)) stop("institution_members_changed", call. = FALSE)
        for (id in preview$ids) {
          public <- desktop_catalog_editor_refresh_v1(asset_center_catalog_editor, runtime$context)
          row <- Filter(function(item) identical(asset_center_account_id(item$ref), id), public$accounts)[[1L]]
          form <- list(action = "update", entity_type = "account", entity_ref = row$ref, portfolio_ref = "", display_name = row$display_name, base_currency = "EUR",
            account_type = row$account_type, institution_label = preview$name, asset_type = "other", price_currency = "EUR", quantity_scale = "0",
            valuation_method = "transaction_only", isin = "")
          step <- desktop_catalog_editor_prepare_v1(asset_center_catalog_editor, runtime$context, form, now_utc())
          desktop_catalog_editor_execute_v1(asset_center_catalog_editor, runtime$context, step, TRUE)
          done <- done + 1L
        }
      }, error = function(error) failure <<- if (identical(conditionMessage(error), "institution_members_changed")) "changed" else "failed")
      preview_value(NULL)
      invisible(tryCatch(asset_center_refresh(input$asset_center_asset), error = function(error) NULL))
      if (is.null(failure)) {
        written_at <<- Sys.time()
        shiny::updateTextInput(session, "asset_center_institution_name", value = "")
        # Freistellungsauftrag, Quellensteuer und Verlusttoepfe haengen am Namen des Instituts und ziehen mit um.
        carried <- if (is.null(institution_tax_service)) NULL else tryCatch(institution_tax_service$rename(preview$old, preview$name, now_utc(), TRUE),
          error = function(error) NULL)
        # Die Art des Instituts (#430) zieht ebenso mit; scheitert das, bleibt sie beim alten Namen und laesst sich neu setzen.
        kind_carried <- if (is.null(institution_master_service)) NULL else tryCatch(institution_master_service$rename(preview$old, preview$name, now_utc(), TRUE),
          error = function(error) NULL)
        if (!is.null(institution_master_area)) institution_master_area$refresh()
        carry_text <- paste0(if (is.null(carried)) " Die Steuerangaben je Institut ließen sich nicht mitnehmen – bitte in „4. Steuer“ prüfen."
          else if (as.integer(carried$kept_count) > 0L) sprintf(" %d Steuerangabe(n) je Institut blieben beim vorhandenen Institut, weil es dort schon eine gab.", as.integer(carried$kept_count))
          else "", if (!is.null(institution_master_service) && is.null(kind_carried)) " Die Art des Instituts ließ sich nicht mitnehmen – bitte unter „Institute · Art und Konten“ neu setzen." else "")
        state(list(tone = "positive", title = "Institut umbenannt", copy = sprintf("„%s“ heißt jetzt „%s“.", preview$old, preview$name)))
        notice_value(list(tone = if (is.null(carried) || (!is.null(institution_master_service) && is.null(kind_carried))) "warning" else "positive", title = sprintf("Institut „%s“ heißt jetzt „%s“", preview$old, preview$name),
          copy = paste0(sprintf("%d Konto/Konten umbenannt. Steuer-Karten und Auszugsablage gliedern ab jetzt unter dem neuen Namen.", done), carry_text)))
        invisible(read_workspace())
      } else notice_value(list(tone = "error", title = "Institut nicht umbenannt", copy = if (identical(failure, "changed"))
          "Die Konten des Instituts haben sich seit der Prüfung geändert. Bitte erneut prüfen."
        else sprintf("Nach %d von %d Konten abgebrochen; die übrigen tragen noch den bisherigen Namen. Bitte erneut prüfen und speichern.", done, length(preview$ids))))
    }
    shiny::observeEvent(input[[paste0("asset_center_", kind, "_prepare")]], {
      if (account && identical(input$asset_center_account_action, "rename_institution")) return(institution_prepare())
      form <- asset_center_inline_form(kind); blocker <- asset_center_inline_blocker(kind, form)
      if (!is.null(blocker)) return(notice_error(paste(label, "nicht geprüft"), blocker))
      number <- if (account) data_account_reference_text_v1(input$asset_center_account_number) else NULL
      if (account && !data_account_reference_number_valid_v1(number)) return(notice_error(paste(label, "nicht geprüft"), data_account_reference_error_text_v1("account_reference_input_invalid")))
      previous <- asset_center_inline_row(kind, form$entity_ref)
      previous_number <- if (account && !is.null(previous)) asset_center_account_number_of(asset_center_account_id(previous$ref)) else NULL
      number_changed <- account && !identical(number, previous_number)
      number_row <- if (account) list(c("Kontonummer", if (!number_changed) (if (is.null(number)) "—" else paste(number, "(unverändert)"))
        else if (is.null(number)) sprintf("wird entfernt (bisher %s)", previous_number) else if (is.null(previous_number)) number else sprintf("%s (bisher %s)", number, previous_number)))
      # Nur die Kontonummer geaendert: Die Stammdaten bleiben, geschrieben wird allein neben ihnen.
      if (account && identical(form$action, "update") && !is.null(previous) && identical(form$display_name, previous$display_name) &&
          identical(form$institution_label, if (is.null(previous$institution_label)) "" else trimws(previous$institution_label))) {
        if (!number_changed) return(notice_error(paste(label, "nicht geprüft"), "Nichts geändert – Bezeichnung, Institut und Kontonummer stimmen mit dem gespeicherten Stand überein."))
        preview_value(list(kind = "number_only", id = asset_center_account_id(previous$ref), name = previous$display_name, number = number,
          institution = form$institution_label, table = as_table(c(list(c("Vorgang", "Kontonummer ändern"), c("Konto", previous$display_name)), number_row,
            list(c("Wirkung", "Die Kontonummer steht neben den Stammdaten; Konto, Buchungen und Bestände bleiben unverändert."))))))
        return(checked_notice())
      }
      checked <- FALSE
      safe(desktop_catalog_editor_prepare_v1(asset_center_catalog_editor, runtime$context, form, now_utc()), function(preview) {
        checked <<- TRUE
        rows <- list(c("Vorgang", if (identical(form$action, "create")) paste(label, "neu anlegen") else paste(label, "umbenennen")))
        if (!is.null(previous)) rows <- c(rows, list(c("Bisherige Bezeichnung", previous$display_name)))
        rows <- c(rows, list(c("Bezeichnung", form$display_name)))
        if (account) {
          if (identical(form$action, "create")) {
            portfolio <- asset_center_inline_row("portfolio", form$portfolio_ref)
            rows <- c(rows, list(c("Portfolio", if (is.null(portfolio)) "" else portfolio$display_name), c("Kontoart", asset_center_account_type_label[[form$account_type]])))
          }
          rows <- c(rows, list(c("Institut / Börse", if (nzchar(form$institution_label)) form$institution_label else "—")), number_row)
        } else if (identical(form$action, "create")) rows <- c(rows, list(c("Portfolio-Währung", form$base_currency), c("Hinweis", "Ein neues Portfolio ist ein eigener, getrennter Bestand. Die Transaktionsmaske bleibt beim oben gewählten Portfolio, bis Sie es umstellen.")))
        rows <- c(rows, list(c("Wirkung", if (identical(form$action, "create")) "Neuer Datensatz; sofort auswählbar." else "Nur die Anzeige ändert sich; Buchungen und Bestände bleiben zugeordnet. Die Änderung wird als neue Fassung auditiert.")))
        preview$table <- as_table(rows)
        if (account) { preview$number <- number; preview$number_changed <- number_changed; preview$target_id <- if (is.null(previous)) NULL else asset_center_account_id(previous$ref) }
        preview_value(preview)
        checked_notice()
      })
      if (!checked) { preview_value(NULL); notice_failure(paste(label, "nicht geprüft")) }
    })
    output[[paste0("asset_center_", kind, "_preview")]] <- shiny::renderTable({ preview <- preview_value(); if (is.null(preview)) NULL else preview$table },
      bordered = TRUE, striped = TRUE, spacing = "xs")
    # Die Kontonummer schreiben; NULL heisst gespeichert, sonst der Grund in Worten.
    record_number <- function(id, number) {
      if (is.null(account_reference_service) || is.null(id)) return(data_account_reference_error_text_v1("account_reference_store_invalid"))
      result <- tryCatch(account_reference_service$record(id, if (is.null(number)) "" else number, now_utc(), TRUE),
        spot_data_account_reference_error_v1 = function(error) error$code, error = function(error) "account_reference_store_invalid")
      if (is.character(result)) data_account_reference_error_text_v1(result) else { account_reference_area$refresh(); NULL }
    }
    shiny::observeEvent(input[[paste0("asset_center_", kind, "_execute")]], {
      preview <- preview_value()
      if (is.null(preview)) {
        state(list(tone = "error", title = paste(label, "nicht gespeichert"), copy = "Bitte zuerst „Prüfen“ ausführen. (Code: desktop_catalog_preview_required)"))
        notice_value(list(tone = "error", title = paste(label, "nicht gespeichert"),
          copy = "Bitte zuerst „Prüfen“ drücken. Gespeichert wird nur, was geprüft ist; jede Änderung am Formular verlangt eine neue Prüfung."))
        return()
      }
      if (identical(preview$kind, "institution")) return(institution_execute(preview))
      if (identical(preview$kind, "number_only")) {
        problem <- record_number(preview$id, preview$number)
        preview_value(NULL)
        if (!is.null(problem)) return(notice_value(list(tone = "error", title = "Kontonummer nicht gespeichert", copy = problem)))
        written_at <<- Sys.time()
        return(notice_value(list(tone = "positive", title = sprintf("Kontonummer von „%s“ gespeichert", preview$name),
          copy = if (is.null(preview$number)) "Die Kontonummer ist entfernt." else sprintf("Kontonummer: %s. Konto, Buchungen und Bestände bleiben unverändert.", preview$number))))
      }
      bound <- preview; bound$table <- NULL; bound$number <- NULL; bound$number_changed <- NULL; bound$target_id <- NULL
      written <- FALSE
      # Was geschrieben wird, steht in der geprüften Vorschau - von dort kommt der Wortlaut der Meldung.
      shown <- stats::setNames(as.character(preview$table$Wert), as.character(preview$table$Feld))
      safe(desktop_catalog_editor_execute_v1(asset_center_catalog_editor, runtime$context, bound, TRUE), function(result) {
        written <<- TRUE
        preview_value(NULL)
        asset_center_refresh(input$asset_center_asset)
        target <- tryCatch(desktop_catalog_editor_preview_target_ref_v1(asset_center_catalog_editor, runtime$context, bound), error = function(error) "")
        if (nzchar(target)) {
          if (account) shiny::updateSelectInput(session, "asset_center_custody_account", selected = target)
          else { shiny::updateSelectInput(session, "asset_center_portfolio", selected = target); asset_center_selected_portfolio_ref <<- target }
        }
        if (identical(result$action, "create")) {
          shiny::updateTextInput(session, paste0("asset_center_", kind, "_name"), value = "")
          if (account) shiny::updateTextInput(session, "asset_center_account_number", value = "")
        }
        # Die Kontonummer kommt nach den Stammdaten - an die Kennung des eben geschriebenen Kontos.
        problem <- if (account && isTRUE(preview$number_changed)) record_number(if (nzchar(target)) asset_center_account_id(target) else preview$target_id, preview$number) else NULL
        invisible(tryCatch(cash_import_load(), error = function(error) NULL))
        state(list(tone = "positive", title = if (identical(result$action, "create")) paste(label, "angelegt") else paste(label, "umbenannt"),
          copy = if (account) "Das Konto ist ausgewählt und steht für die nächste Transaktion bereit." else "Das Portfolio ist ausgewählt."))
        written_at <<- Sys.time()
        notice_value(list(tone = if (is.null(problem)) "positive" else "warning",
          title = sprintf("%s „%s“ %s", label, shown[["Bezeichnung"]], if (identical(result$action, "create")) "angelegt" else "umbenannt"),
          copy = paste0(
            if (account && "Institut / Börse" %in% names(shown)) sprintf("Institut / Börse: %s. ", shown[["Institut / Börse"]]) else "",
            if (account && isTRUE(preview$number_changed) && is.null(problem)) (if (is.null(preview$number)) "Kontonummer entfernt. " else sprintf("Kontonummer: %s. ", preview$number)) else "",
            if (!is.null(problem)) paste("Die Kontonummer ist nicht gespeichert:", problem, "") else "",
            if (account) "Das Konto ist oben ausgewählt und steht für die nächste Transaktion bereit." else "Das Portfolio ist oben ausgewählt.")))
        invisible(read_workspace())
      })
      if (!written) notice_failure(paste(label, "nicht gespeichert"))
    })
  })
  # Die Auswahlen am Kontoformular folgen den Stammdaten: Nach jedem Lesen des Katalogs stehen die vorhandenen Konten und
  # Institute zur Wahl; eine gerade eingetippte Angabe bleibt stehen, das gewaehlte Konto bleibt gewaehlt.
  shiny::observeEvent(asset_center_catalog(), {
    model <- asset_center_catalog(); accounts <- if (is.null(model)) list() else model$accounts
    current <- shiny::isolate(input$asset_center_account_institution)
    choices <- data_asset_center_institution_choices_v1(accounts, keep = current)
    shiny::updateSelectizeInput(session, "asset_center_account_institution", choices = choices,
      selected = if (is.character(current) && length(current) == 1L && current %in% choices) current else "")
    target <- asset_center_account_ref_of(asset_center_account_target_id)
    shiny::updateSelectInput(session, "asset_center_account_target", choices = data_asset_center_account_choices_v1(accounts), selected = target)
    institutions <- data_asset_center_institution_choices_v1(accounts)
    held <- shiny::isolate(input$asset_center_institution_target)
    shiny::updateSelectInput(session, "asset_center_institution_target", choices = c(`Bitte wählen` = "", institutions[nzchar(institutions)]),
      selected = if (is.character(held) && length(held) == 1L && held %in% institutions) held else "")
  }, ignoreNULL = FALSE)
  shiny::observeEvent(input$asset_center_account_target, {
    asset_center_account_target_id <<- asset_center_account_id(input$asset_center_account_target)
  }, ignoreNULL = FALSE, ignoreInit = TRUE)
  # Die durchsuchbare Kontenliste mit Institut und Kontonummer. Die Kennung des Kontos bleibt im Prozess.
  account_reference_area <- data_account_reference_server_v1(input, output, session, account_reference_service,
    accounts = asset_center_accounts,
    resolve_id = function(ref) desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "account", ref),
    wallet_entries = if (is.null(fifo_wallet_service)) NULL else function() fifo_wallet_service$entries())
  # Ablage der Original-Auszuege: Dokumente je Institut und Konto, Monatsraster je Jahr.
  data_statement_archive_server_v1(input, output, session, statement_archive_service,
    accounts = function() { model <- asset_center_catalog(); if (is.null(model)) list() else model$accounts },
    resolve_id = function(ref) desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "account", ref))
  asset_center_selected <- function() {
    catalog <- asset_center_catalog()
    if (is.null(catalog)) return(NULL)
    tryCatch(data_asset_center_selected_v1(catalog, input$asset_center_asset), error = function(e) NULL)
  }
  asset_center_selected_id <- function() {
    if (is.null(asset_center_selected())) return(NULL)
    desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", input$asset_center_asset)
  }
  asset_center_require_market <- function(mapping = FALSE) {
    asset <- asset_center_selected()
    if (!identical(input$asset_center_mode, "existing") || is.null(asset) || !identical(asset$valuation_method, "external_market") || !identical(asset$status, "active"))
      stop("asset_center_market_method_invalid", call. = FALSE)
    if (mapping) {
      private <- .data_provider_mapping_state_v1(asset_center_provider_editor, runtime$context)$mapping_map[[input$asset_center_mapping]]
      if (is.null(private) || !identical(private$asset_id, asset_center_selected_id())) stop("asset_center_market_selection_invalid", call. = FALSE)
    }
    invisible(TRUE)
  }
  asset_center_require_search <- function() {
    if (identical(input$asset_center_mode, "new")) {
      if (!identical(input$asset_center_valuation, "external_market") || identical(input$asset_center_type, "cash"))
        stop("asset_center_market_method_invalid", call. = FALSE)
      return(invisible(TRUE))
    }
    asset_center_require_market()
  }
  asset_center_reset_confirmations <- function() {
    for (reset in list(asset_center_edit_preview, asset_center_price_currency_preview,
      asset_center_provider_preview, asset_center_provider_search_preview, asset_center_provider_search_result,
      asset_center_provider_probe_preview, asset_center_provider_probe_result,
      asset_center_provider_promotion_preview, asset_center_provider_promotion_result,
      asset_center_mapping_verify_preview, asset_center_market_plan, asset_center_market_fetch_preview,
      asset_center_market_fetch_result, asset_center_market_review, asset_center_market_publication_result)) reset(NULL)
    for (suffix in c("edit", "price_currency", "provider", "provider_search", "provider_probe", "promotion",
      "mapping_verify", "history_fetch", "history_publish", "history_reject"))
      shiny::updateCheckboxInput(session, paste0("asset_center_", suffix, "_confirm"), value = FALSE)
    shiny::updateSelectInput(session, "asset_center_provider_candidate", choices = c("Noch keine Vorschläge" = ""), selected = "")
  }
  # Anbieter der Kurszuordnung waehlen (rc.394): Die Auswahl enthaelt ihn, auch wenn er nicht (mehr) aktiv ist.
  asset_center_select_provider <- function(provider_id) {
    choices <- data_asset_center_history_providers_v1(asset_center_price_provider_rows(), provider_id)
    shiny::updateSelectInput(session, "asset_center_provider_id", choices = choices, selected = provider_id)
  }
  asset_center_apply_provider_draft <- function(value) {
    asset_center_currency_auto_value <<- value$provider_currency
    asset_center_select_provider(value$provider_id)
    fields <- c(symbol = "provider_symbol", currency = "provider_currency", exchange = "exchange_code", mic = "mic_code")
    for (suffix in names(fields))
      shiny::updateTextInput(session, paste0("asset_center_provider_", suffix), value = value[[fields[[suffix]]]])
  }
  asset_center_apply_master_draft <- function(value) {
    shiny::updateTextInput(session, "asset_center_edit_name", value = value$display_name)
    shiny::updateTextInput(session, "asset_center_edit_isin", value = value$isin)
    shiny::updateTextInput(session, "asset_center_price_currency_target", value = value$price_currency)
  }
  asset_center_select_defaults <- function(ref) {
    asset_center_reset_confirmations()
    selected <- tryCatch(data_asset_center_selected_v1(asset_center_catalog(), ref), error = function(e) NULL)
    if (is.null(selected)) return(invisible(NULL))
    mappings <- data_asset_center_provider_rows_v1(asset_center_provider_catalog(), ref)
    choices <- data_market_mapping_choices_v1(mappings)
    daily <- Filter(function(r) identical(r$capability, "daily_history"), mappings)
    mapping <- if (length(daily)) daily[[1L]] else NULL
    shiny::updateSelectInput(session, "asset_center_mapping", choices = choices, selected = if (is.null(mapping)) "" else mapping$ref)
    shiny::updateSelectInput(session, "asset_center_provider_action", selected = if (is.null(mapping)) "create" else "revise")
    defaults <- data_market_defaults_v1(selected, mapping = mapping)
    asset_center_apply_provider_draft(defaults)
    asset_center_defaults_notice(paste(defaults$currency_basis, "· Kalender ist ein prüfpflichtiger Vorschlag; Marktcode und Zeitzone nicht erfunden."))
    shiny::updateSelectInput(session, "asset_center_provider_capability", selected = "daily_history")
    shiny::updateCheckboxInput(session, "asset_center_provider_expert", value = FALSE)
    shiny::updateTextInput(session, "asset_center_listing_market", value = "")
    shiny::updateTextInput(session, "asset_center_listing_timezone", value = "")
    shiny::updateSelectInput(session, "asset_center_listing_calendar", selected = defaults$calendar)
    isin <- if (is.null(selected$isin)) "" else selected$isin
    shiny::updateTextInput(session, "asset_center_provider_query", value = if (nzchar(isin)) isin else selected$display_name)
    shiny::updateSelectInput(session, "asset_center_search_provider", selected = "yahoo")
    shiny::updateSelectInput(session, "asset_center_provider_search_mode", selected = if (nzchar(isin)) "isin" else "name")
    asset_center_apply_master_draft(list(display_name = selected$display_name, isin = isin, price_currency = selected$price_currency))
    if (!is.null(asset_center_pending_draft) && identical(asset_center_pending_draft$ref, ref)) {
      pending <- asset_center_pending_draft; asset_center_pending_draft <<- NULL
      if (!is.null(pending$draft)) {
        if (is.null(mapping)) {
          asset_center_apply_provider_draft(pending$draft)
          # Restored owner input is not a fresh automatic currency suggestion.
          asset_center_currency_auto_value <<- NULL
          asset_center_defaults_notice("Wiederhergestellter unbestätigter Entwurf · keine Providerinformation und keine gespeicherte Bestätigung.")
        }
      }
    }
    # A preceding catalog-selection message may arrive before the requested
    # queue selection. Keep its bound draft until that exact asset is selected.
  }
  worklist_inventory <- function(fresh = FALSE) {
    core <- asset_center_catalog(); providers <- asset_center_provider_catalog()
    if (is.null(core) || is.null(providers)) return(list())
    private <- .data_provider_mapping_state_v1(asset_center_provider_editor, runtime$context)
    current_assets <- if (fresh) catalog_read_v1(runtime$context)$assets else NULL
    current_mappings <- if (fresh) provider_mapping_read_v1(runtime$context)$mappings else unname(private$mapping_map)
    Filter(Negate(is.null), lapply(core$assets, function(row) {
      key <- desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", row$ref)
      if (fresh) {
        current <- Filter(function(r) identical(r$asset_id, key), current_assets)
        if (length(current) != 1L) return(NULL)
        ref <- row$ref; row <- current[[1L]]; row$ref <- ref
      }
      mappings <- Filter(function(r) identical(r$asset_id, key) && identical(r$capability, "daily_history"), current_mappings)
      verified <- any(vapply(mappings, function(r) identical(r$verification_status, "verified") && r$enabled == 1L, logical(1L)))
      list(asset_id = key, asset_ref = row$ref, label = row$display_name,
        eligible = identical(row$status, "active") && identical(row$valuation_method, "external_market"), missing = !length(mappings),
        mapping_label = if (verified) "Verifiziert" else if (length(mappings)) "Zuordnung vorhanden · Test/Aktivierung prüfen" else "Zuordnung fehlt")
    }))
  }
  worklist_choose <- function(ref, draft, domain) {
    asset_center_pending_draft <<- list(ref = ref, draft = draft, domain = domain)
    shiny::updateRadioButtons(session, "asset_center_mode", selected = "existing")
    shiny::updateTabsetPanel(session, "asset_center_step", selected = "Marktdaten")
    if (identical(ref, input$asset_center_asset)) asset_center_select_defaults(ref)
    else asset_center_select(ref)
  }
  provider_worklist <- data_asset_worklist_server_v1(input, output, session, "market_worklist", market_worklist_service,
    worklist_inventory, worklist_choose, asset_center_selected_id, function() list(provider_id = input$asset_center_provider_id,
      provider_symbol = input$asset_center_provider_symbol, provider_currency = toupper(input$asset_center_provider_currency),
      exchange_code = input$asset_center_provider_exchange, mic_code = toupper(input$asset_center_provider_mic)),
    verify_inventory = function() worklist_inventory(TRUE))
  shiny::observeEvent(input$asset_center_asset, {
    asset_center_activity_state("not_checked")
    asset_center_select_defaults(input$asset_center_asset)
    pending <- shiny::isolate(asset_center_pending_isin())
    if (is.list(pending) && identical(pending$ref, input$asset_center_asset)) {
      shiny::updateTextInput(session, "asset_center_edit_isin", value = pending$isin); asset_center_pending_isin(NULL)
    }
    if (isTRUE(asset_center_tax_service$initialized())) asset_center_tax_state("not_configured")
  }, ignoreInit = TRUE, priority = 100)
  shiny::observeEvent(input$asset_center_edit_prepare, safe({
    form <- asset_center_edit_form()
    preview <- desktop_catalog_editor_prepare_v1(asset_center_catalog_editor, runtime$context, form, now_utc())
    list(preview = preview, form = form, prior = asset_center_selected())
  }, function(value) { asset_center_edit_preview(value); shiny::updateCheckboxInput(session, "asset_center_edit_confirm", value = FALSE) }))
  shiny::observeEvent(input$asset_center_edit_execute, safe({
    value <- asset_center_edit_preview()
    if (is.null(value) || !identical(value$form, asset_center_edit_form())) stop("desktop_catalog_preview_required", call. = FALSE)
    desktop_catalog_editor_execute_v1(asset_center_catalog_editor, runtime$context, value$preview, isTRUE(input$asset_center_edit_confirm))
  }, function(result) {
    asset_center_edit_preview(NULL); shiny::updateCheckboxInput(session, "asset_center_edit_confirm", value = FALSE)
    invisible(asset_center_refresh(input$asset_center_asset))
    if (identical(result$action, "set_isin") && !is.null(securities_import_return())) securities_import_return_after_create()
    else if (identical(result$action, "set_isin")) state(list(tone = "positive", title = "ISIN nachgetragen", copy = "Die Kursfreigabe bleibt gültig · keine Änderung an Buchungen, FIFO oder Marktdaten. Nach Prüfung in der Arbeitsliste weitergehen."))
    else state(list(tone = "positive", title = "Stammdaten korrigiert", copy = "Neue Fassung auditiert · keine Änderung an Buchungen, FIFO oder Marktdaten. Nach Prüfung in der Arbeitsliste weitergehen."))
  }))
  shiny::observeEvent(list(input$asset_center_edit_name, input$asset_center_edit_isin), {
    asset_center_edit_preview(NULL); shiny::updateCheckboxInput(session, "asset_center_edit_confirm", value = FALSE)
  }, ignoreInit = TRUE)
  output$asset_center_edit_preview <- shiny::renderTable({
    value <- asset_center_edit_preview(); if (is.null(value)) return(data.frame())
    data.frame(Feld = c("Bezeichnung", "ISIN"), Bisher = c(value$prior$display_name, if (is.null(value$prior$isin)) "" else value$prior$isin),
      Neu = c(value$form$display_name, value$form$isin), check.names = FALSE)
  })
  asset_center_currency_suggestion <- function() {
    asset<-asset_center_selected()
    data_market_currency_suggestion_v1(input$asset_center_provider_id,input$asset_center_provider_symbol,if(is.null(asset))''else asset$price_currency)
  }
  shiny::observeEvent(list(input$asset_center_provider_symbol,input$asset_center_provider_id), {
    if(!identical(input$asset_center_provider_action,'create')||(!is.null(input$asset_center_mapping)&&nzchar(input$asset_center_mapping)))return()
    current<-input$asset_center_provider_currency
    if(!is.null(current)&&nzchar(current)&&!identical(current,asset_center_currency_auto_value))return()
    hint<-asset_center_currency_suggestion();asset_center_currency_auto_value<<-hint$currency
    if(!identical(current,hint$currency))session$sendCustomMessage('asset_center_currency_proposal',list(
      currency=hint$currency,expected_currency=if(is.null(current))''else current,
      symbol=input$asset_center_provider_symbol,provider=input$asset_center_provider_id,asset=input$asset_center_asset))
    asset_center_defaults_notice(hint$basis)
  },ignoreInit=TRUE)
  shiny::observeEvent(input$asset_center_currency_suggest, {
    hint<-asset_center_currency_suggestion()
    asset_center_currency_auto_value<<-hint$currency
    shiny::updateTextInput(session,'asset_center_provider_currency',value=hint$currency)
    asset_center_defaults_notice(paste(hint$basis,'· nur Formular geändert; nicht gespeichert.'))
  })
  output$asset_center_defaults_notice <- shiny::renderUI(shiny::tagList(shiny::p(asset_center_defaults_notice()),shiny::p(asset_center_currency_suggestion()$basis)))
  shiny::observeEvent(list(input$asset_center_asset,input$asset_center_mode), {
    action_feedback$clear(c('method','search','candidate','mapping','probe','promotion','verification'))
  },ignoreInit=TRUE,priority=200)
  shiny::observeEvent(list(input$asset_center_mapping), {
    action_feedback$clear(c('probe','promotion','verification'))
  },ignoreInit=TRUE,priority=200)
  for(phase in c('mapping','probe','promotion','verification')) local({
    name <- phase
    output[[paste0(name,'_action_hint')]] <- shiny::renderUI({
      model <- asset_center_provider_catalog()
      rows <- if(is.null(model))list()else Filter(function(r)identical(r$ref,input$asset_center_mapping)&&identical(r$asset_ref,input$asset_center_asset),model$mappings)
      mapped <- length(rows)==1L
      verified <- mapped && identical(rows[[1L]]$verification_status,'verified') && isTRUE(rows[[1L]]$enabled)
      preview <- switch(name,mapping=asset_center_provider_preview(),probe=asset_center_provider_probe_preview(),promotion=asset_center_provider_promotion_preview(),verification=asset_center_mapping_verify_preview())
      value <- data_provider_action_hint_v1(name,mapped,verified,!is.null(preview),!is.null(asset_center_provider_probe_result()),!is.null(asset_center_provider_promotion_result()))
      shiny::p(class='pl-section-copy',shiny::strong(paste(value$title, '·')),value$copy)
    })
  })
  # Welcher Unterreiter der Marktdaten ist fuer das gewaehlte Asset dran (#422, rc.333)? Nach Bewertungsart: Provider-Kurse
  # brauchen Kursquelle -> Einrichten -> Bewerten; eigene Kursangaben Kursquelle -> Bewerten; Einheitswert nur Bewerten.
  # Massgeblich ist die Tageshistorie-Zuordnung des Assets, nicht die gerade im Formular gewaehlte.
  asset_center_market_step <- function() {
    asset <- tryCatch(asset_center_selected(), error = function(error) NULL)
    if (is.null(asset)) return(NULL)
    method <- if (is.character(asset$valuation_method)) asset$valuation_method else "external_market"
    if (identical(method, "manual")) return(list(value = "source", title = "Eigene Kurse · erst eintragen, dann bewerten",
      copy = "Unter „1. Kursquelle“ eigene Kursangaben eintragen oder bestätigte Trade-Stückpreise wählen, dann unter „3. Bewerten“ rechnen."))
    if (identical(method, "unit_value")) return(list(value = "valuation", title = "Einheitswert · nur bewerten",
      copy = "Eine Kursquelle ist nicht nötig; unter „3. Bewerten“ rechnen."))
    if (identical(method, "transaction_only")) return(list(value = "source", title = "Nur Transaktionen · keine Kursbewertung",
      copy = "Dieses Asset wird nicht mit Kursen bewertet. Ändern lässt sich das unter „1. Kursquelle“ in der Karte „Bewertung über die Zeit“."))
    model <- asset_center_provider_catalog()
    rows <- if (is.null(model)) list() else Filter(function(r) identical(r$asset_ref, asset$ref) && identical(r$capability, "daily_history"), model$mappings)
    if (!length(rows)) return(list(value = "source", title = "Schritt 1 von 3 · Kursquelle",
      copy = "Anbieter, Symbol und Kurswährung eintragen, dann „Zuordnung speichern“. Die Suche hilft, das Symbol zu finden."))
    if (any(vapply(rows, function(r) identical(r$verification_status, "verified") && isTRUE(r$enabled), logical(1L))))
      return(list(value = "valuation", title = "Schritt 3 von 3 · Bewerten",
        copy = "„Prüfen, was fehlt“ und anschließend den Knopf daneben. Der Lauf hält mit einer Vorschau an; erst „Bewertung abschließen“ schreibt sie."))
    list(value = "setup", title = "Schritt 2 von 3 · Einrichten", copy = "„Jetzt einrichten“: ein Testabruf, dann Freigabe und Verifizierung in einem Zug.")
  }
  MARKET_SECTION_LABELS <- c(source = "1. Kursquelle", setup = "2. Einrichten", valuation = "3. Bewerten", problems = "Bei Problemen")
  output$asset_center_provider_next_step <- shiny::renderUI({
    step <- asset_center_market_step(); if (is.null(step)) return(NULL)
    # Als kleiner Fliesstext war der Hinweis nicht zu finden; er steht im selben Kasten wie die Rueckmeldungen
    # (Festlegung 21.09.2026). Steht der Reiter woanders, fuehrt ein Knopf hin.
    elsewhere <- !identical(input$market_section, step$value)
    shiny::div(role='status',`aria-live`='polite',`aria-atomic`='true',
      portelyra_status_panel(step$title, step$copy, tone='neutral'),
      if (elsewhere) data_market_next_v1(step$value, MARKET_SECTION_LABELS[[step$value]]))
  })
  # Beim Oeffnen der Marktdaten und beim Wechsel des Assets den Schritt zeigen, der dran ist - ausser man arbeitet gerade
  # unter "Bei Problemen". Nach einem Schritt weiter geht es per Klick ("Weiter"), damit die Rueckmeldung stehen bleibt.
  # Eine eigene Wahl geht vor (#579): Hat man im selben Zug einen Unterreiter gewaehlt - ein beschaeftigter Server verarbeitet den Klick auf
  # "Marktdaten" und auf "3. Bewerten" gemeinsam -, bleibt es dabei; der Merker laeuft nach den Spruengen (Prioritaet). Im Browser wechselt
  # der Reiter nur, wenn er noch auf dem Stand steht, den der Server kannte - ein Klick kann gerade unterwegs sein (pl_set_if_unchanged).
  market_section_seen <- NULL
  market_section_follow <- function() {
    if (!identical(input$asset_center_step, "Marktdaten") || identical(input$market_section, "problems")) return(invisible(NULL))
    if (!is.null(market_section_seen) && !identical(input$market_section, market_section_seen)) return(invisible(NULL))
    step <- asset_center_market_step(); if (is.null(step) || identical(input$market_section, step$value)) return(invisible(NULL))
    session$sendCustomMessage("pl_set_if_unchanged", list(kind = "tab", id = "market_section", value = step$value, expected = input$market_section %||% ""))
  }
  shiny::observeEvent(input$asset_center_step, market_section_follow(), ignoreInit = TRUE, priority = 10)
  shiny::observeEvent(input$asset_center_asset, market_section_follow(), ignoreInit = TRUE, priority = 10)
  shiny::observeEvent(input$market_section, market_section_seen <<- input$market_section, priority = -10)
  output$asset_center_history_has_ranges <- shiny::renderText({
    p<-asset_center_market_plan()
    if(!is.null(p)&&p$target_day_count>0L&&identical(p$mode,input$asset_center_history_mode)&&identical(p$required_start_date,as.character(input$asset_center_history_start))&&identical(p$as_of_date,as.character(input$asset_center_history_end)))'yes'else 'no'
  })
  shiny::outputOptions(output,'asset_center_history_has_ranges',suspendWhenHidden=FALSE)
  output$asset_center_history_plan_guidance <- shiny::renderUI({
    p<-asset_center_market_plan()
    shiny::p(if(is.null(p))'Zuerst „Zeiträume nur lesend planen“. Nach einem Neustart ist die sitzungslokale Planung erneut nötig.'else if(!identical(p$mode,input$asset_center_history_mode)||!identical(p$required_start_date,as.character(input$asset_center_history_start))||!identical(p$as_of_date,as.character(input$asset_center_history_end)))'Zeitraum oder Modus geändert: Plan erneut nur lesend erstellen.'else if(p$target_day_count==0L)'Kein Abruf erforderlich. Gespeicherte Quelllücken bleiben separat zu prüfen; Nullplan bedeutet nicht lückenlose Kurswerte.'else 'Genau einen geplanten Bereich prüfen, danach den Abruf separat bestätigen.')
  })
  output$asset_center_external_market <- shiny::renderText({
    selected <- asset_center_selected()
    if (identical(input$asset_center_mode, "existing") && !is.null(selected) && identical(selected$status, "active") && identical(selected$valuation_method, "external_market")) "yes" else "no"
  })
  shiny::outputOptions(output, "asset_center_external_market", suspendWhenHidden = FALSE)
  # Die Bewertungsart eines bestehenden Assets aendert seit rc.393 allein die Karte "Bewertung ueber die Zeit" - fuer die ganze
  # Zeit ("Ganze Historie neu") oder ab einem Tag. Den zweiten Weg "Bewertungsart aendern" gibt es nicht mehr (Festlegung 10.11.2026).
  output$asset_center_unmapped <- shiny::renderUI({
    if(is.null(asset_center_catalog()))return(NULL)
    rows <- data_asset_center_market_inventory_v1(asset_center_catalog(),asset_center_provider_catalog())$rows
    rows <- Filter(function(row)identical(row$status,'mapping_missing'),rows)
    choices <- c('Asset auswählen…'='',stats::setNames(vapply(rows,`[[`,character(1),'asset_ref'),vapply(rows,`[[`,character(1),'asset_name')))
    shiny::tagList(shiny::selectInput('asset_center_unmapped_choice','Assets ohne Providerzuordnung',choices),
      shiny::actionButton('asset_center_unmapped_select','Dieses Asset bearbeiten'),
      shiny::p('Nur Assets mit Bewertung über einen Kursanbieter. Die Auswahl startet keinen Abruf.'))
  })
  shiny::observeEvent(input$asset_center_unmapped_select, {
    rows <- data_asset_center_market_inventory_v1(asset_center_catalog(),asset_center_provider_catalog())$rows
    refs <- vapply(Filter(function(row)identical(row$status,'mapping_missing'),rows),`[[`,character(1),'asset_ref')
    if(input$asset_center_unmapped_choice %in% refs) shiny::updateSelectInput(session,'asset_center_asset',selected=input$asset_center_unmapped_choice)
  })
  # Bewertung ueber die Zeit (rc.393, #495): gelesen erst, wenn "3. Marktdaten" -> "1. Kursquelle" offen ist und ein bestehendes Asset
  # gewaehlt ist. Muss die Bewertungsart der Stammdaten mit umgestellt werden, geht es denselben Weg wie "Bewertungsart aendern".
  asset_valuation_timeline_service <- tryCatch(new_data_asset_valuation_timeline_service_v1(project_root, runtime$context), error = function(error) NULL)
  asset_valuation_timeline <- data_asset_valuation_timeline_server_v1(input, output, session, asset_valuation_timeline_service,
    asset = shiny::reactive({
      if (!identical(input$asset_center_mode, "existing")) return(NULL)
      selected <- tryCatch(asset_center_selected(), error = function(error) NULL)
      if (is.null(selected) || !identical(selected$status, "active")) return(NULL)
      asset_id <- tryCatch(asset_center_selected_id(), error = function(error) NULL)
      if (is.null(asset_id)) NULL else list(asset_id = asset_id, ref = selected$ref, display_name = selected$display_name,
                                            valuation_method = selected$valuation_method)
    }),
    active = shiny::reactive(identical(input$asset_center_step, "Marktdaten") && identical(input$market_section, "source")),
    catalog_revise = function(method, ref) {
      form <- asset_center_price_currency_form(); form$action <- "revise_valuation_method"; form$entity_ref <- ref
      form$valuation_method <- method
      prepared <- desktop_catalog_editor_prepare_v1(asset_center_catalog_editor, runtime$context, form, now_utc())
      desktop_catalog_editor_execute_v1(asset_center_catalog_editor, runtime$context, prepared, TRUE)
    },
    on_changed = function() {
      asset_center_refresh(shiny::isolate(input$asset_center_asset)); asset_center_valuation_workflow$invalidate()
    })
  # Eigene Kursangaben auch, wenn die Zeitleiste einen Abschnitt "eigene Kurse" fuehrt (der Kern laesst sie dann zu).
  asset_center_manual_allowed <- function(selected) !is.null(selected) &&
    (identical(selected$valuation_method, "manual") || isTRUE(asset_valuation_timeline$has_manual(selected$ref)))
  output$asset_center_manual_method <- shiny::renderText({
    selected <- tryCatch(asset_center_selected(), error = function(error) NULL)
    if (asset_center_manual_allowed(selected)) "yes" else "no"
  })
  shiny::outputOptions(output, "asset_center_manual_method", suspendWhenHidden = FALSE)
  output$asset_center_market_method <- shiny::renderUI({
    selected <- asset_center_selected(); if (is.null(selected)) return(shiny::p("Zuerst bestehendes Asset auswählen."))
    copy <- switch(selected$valuation_method,
      external_market = "Einstellungen des Kursanbieters und Historie für dieses Asset. Alle externen Aktionen brauchen weiterhin eine Bestätigung.",
      manual = "Manuelle Bewertung, kein Kursanbieter nötig. Nach dem Speichern der Methode wählen Sie unten die Quelle: eigene Kursangaben, die Sie selbst eintragen, oder gespeicherte Stückpreise aus Trades. Beides sind keine Marktkurse und wird als Ersatzwert gekennzeichnet.",
      unit_value = "Einheitswert: kein Providerabruf erforderlich. Die explizite fachliche Währung gilt.",
      transaction_only = "Nur Transaktionen: keine Kursbewertung vorgesehen und keine Providerfelder erforderlich.")
    # Geaendert wird die Bewertungsart allein in der Karte "Bewertung ueber die Zeit" darunter (rc.393): fuer die ganze Zeit oder ab
    # einem Tag. Bis rc.392 stand hier zusaetzlich "Bewertungsart aendern" - zwei Wege, von denen einer die Zeitleiste uebersah.
    shiny::tagList(shiny::p(paste(selected$display_name, "·", copy)),
      shiny::p(class = "pl-field-hint", "Ändern – für die ganze Zeit oder ab einem Tag – in der Karte „Bewertung über die Zeit“ darunter."))
  })
  read_asset_center_coverage <- function() {
    catalog <- asset_center_catalog(); providers <- asset_center_provider_catalog()
    if (is.null(catalog) || is.null(providers)) stop("asset_center_refresh_required", call. = FALSE)
    inventory <- data_asset_center_market_inventory_v1(catalog, providers); bindings <- list()
    for (row in inventory$rows) {
      if (!identical(row$status, "history_ready_to_plan")) next
      scope <- data_provider_mapping_editor_resolve_history_scope_v1(asset_center_provider_editor, runtime$context, row$mapping_ref)
      recovered <- asset_center_provider_promotion_service$recover(scope$mapping_id)
      if (is.null(recovered)) next
      private <- asset_center_provider_promotion_service$resolve_promotion(recovered$promotion_handle)
      bindings[[length(bindings) + 1L]] <- list(asset_ref=row$asset_ref, mapping_ref=row$mapping_ref, listing_ref=private$listing_ref)
    }
    market <- if (!length(bindings)) list(status="ready",asset_count=0L,rows=list(),provider_access=FALSE,network_access=FALSE,market_history_write=FALSE,canonical_write=FALSE) else asset_center_market_coverage_service$read(bindings, as.character(input$asset_center_coverage_start), as.character(input$asset_center_coverage_end))
    demand <- data_asset_center_fx_demand_v1(inventory, input$asset_center_completion_currency)
    fx_bindings <- lapply(demand$rows, function(row) list(source_currency=row$source_currency,target_currency=row$target_currency,consumer_count=as.integer(row$consumer_count)))
    fx <- asset_center_fx_coverage_service$read(fx_bindings, as.character(input$asset_center_coverage_start), as.character(input$asset_center_coverage_end))
    gap_listings<-lapply(bindings,function(row)list(asset_ref=row$asset_ref,listing_ref=row$listing_ref))
    gap_attempt<-data_asset_center_optional_calendar_gap_read_v1(function()asset_center_calendar_gap_service$read(gap_listings,fx_bindings,as.character(input$asset_center_coverage_start),as.character(input$asset_center_coverage_end)))
    targets <- list()
    for (b in bindings) targets[[paste0('listing|',b$asset_ref)]] <- list(kind='listing',listing_ref=b$listing_ref,consumer=b$asset_ref)
    for (b in fx_bindings) targets[[paste0('fx_pair|',b$source_currency,'→',b$target_currency)]] <- list(kind='fx_pair',source=b$source_currency,target=b$target_currency,consumer=paste0(b$source_currency,'→',b$target_currency))
    list(market=market,fx=fx,gaps=gap_attempt$value,calendar_targets=targets,calendar_gap_status=gap_attempt$status,calendar_gap_error_code=gap_attempt$error_code)
  }
  prepare_asset_center_completion <- function() {
    catalog<-asset_center_catalog();providers<-asset_center_provider_catalog()
    if(is.null(catalog)||is.null(providers))stop("asset_center_refresh_required",call.=FALSE)
    data_asset_center_market_fx_completion_plan_v1(data_asset_center_market_inventory_v1(catalog,providers),asset_center_market_coverage(),asset_center_fx_coverage(),as.character(input$asset_center_coverage_start),as.character(input$asset_center_coverage_end),input$asset_center_completion_currency)
  }
  accept_asset_center_coverage <- function(value) {
    asset_center_market_coverage(value$market); asset_center_fx_coverage(value$fx); asset_center_calendar_gaps(value$gaps)
    asset_center_calendar_targets(value$calendar_targets)
    asset_center_calendar_review_service$invalidate()
    asset_center_calendar_binding_preview(NULL); asset_center_calendar_correction_preview(NULL); asset_center_calendar_batch_preview(NULL)
    rows <- if (is.null(value$gaps)) list() else value$gaps$rows
    keys <- unique(vapply(rows,function(r)paste(r$scope_kind,r$consumer_ref,sep='|'),character(1L)))
    labels <- vapply(keys,function(key){t<-value$calendar_targets[[key]]; if(is.null(t))return(key); if(t$kind=='fx_pair')return(paste('FX',t$consumer)); a<-data_asset_center_selected_v1(asset_center_catalog(),t$consumer);paste('Kurs',a$display_name)},character(1L))
    shiny::updateSelectInput(session,'asset_center_calendar_scope',choices=c('Bitte Bereich auswählen'='',stats::setNames(keys,labels)),selected=if(length(input$asset_center_calendar_scope)==1L && input$asset_center_calendar_scope %in% keys)input$asset_center_calendar_scope else '')
    for(id in c('asset_center_calendar_binding_confirm','asset_center_calendar_correction_confirm','asset_center_calendar_batch_confirm'))shiny::updateCheckboxInput(session,id,value=FALSE)
    if(!is.null(asset_center_completion_plan()))asset_center_completion_plan(prepare_asset_center_completion())
    asset_center_completion_batch(NULL)
    state(list(tone=if(identical(value$calendar_gap_status,"blocked"))"warning"else"neutral",title=paste(value$market$asset_count,"Historien geprüft"),copy=if(identical(value$calendar_gap_status,"blocked"))paste("Kurs- und FX-Abdeckung gelesen · optionale Prüfung auf Kalenderlücken getrennt blockiert:",value$calendar_gap_error_code,"· kein Kursabruf · kein Schreiben")else paste("Gespeicherte Kurs- und FX-Abdeckung gelesen ·",value$fx$pair_count,"FX-Bedarfe · kein Kursabruf · kein Schreiben")))
  }
  shiny::observeEvent(input$asset_center_coverage_read,safe(read_asset_center_coverage(),accept_asset_center_coverage))
  shiny::observeEvent(input$asset_center_completion_plan,safe(prepare_asset_center_completion(),function(value){asset_center_completion_plan(value);asset_center_completion_batch(NULL);state(list(tone=if(identical(value$status,"ready_for_snapshot"))"positive"else"warning",title="Abschlussplan für Kurse und FX bereit",copy=paste(value$asset_count,"Assets · nächste Aktion:",value$next_action$label,"· 0 still verworfen · kein Kursabruf · kein Schreiben")))}))
  shiny::observeEvent(input$asset_center_completion_coverage_action,safe(read_asset_center_coverage(),accept_asset_center_coverage))
  output$asset_center_valuation_workspace <- shiny::renderUI(data_market_valuation_ui_v1())
  # Benannte Funktionen, weil ausser dem Bewertungs-Workflow auch die
  # Aktualisierungskette Bestand und Ziele braucht (#283).
  # Die Kurskette und der Sammellauf liegen seit rc.315 (#510) in apps/data/data_market_chain_v1.R: derselbe Code fuer den
  # Einzelablauf, den Sammellauf im Reiter Marktdaten und den Hintergrundlauf von „Alles aktualisieren“. Die Huellen hier
  # liefern nur, was aus der Oberflaeche kommt (Auswahl, Zeitraum) und die Lesestaende der Sitzung.
  # Bewertungs-Zeitleiste (rc.393): Der Sammellauf holt und bewertet jede Kursreihe der Zeitleiste, eine fruehere nur in ihrem
  # Abschnitt. Ohne Speicher der Zeitleiste startet der Leser keinen Prozess.
  asset_center_timeline_reader <- new_data_market_timeline_reader_v1(project_root, runtime$context)
  asset_center_chain <- new_data_market_chain_v1(
    services = list(market_review = asset_center_market_review_service, market_plan = asset_center_market_plan_service,
                    market_coverage = asset_center_market_coverage_service, fx_history = asset_center_fx_history_service,
                    fx_coverage = asset_center_fx_coverage_service, calendar_gap = asset_center_calendar_gap_service,
                    calendar_review = asset_center_calendar_review_service, valuation = asset_center_valuation_service,
                    promotion = asset_center_provider_promotion_service, catalog_editor = asset_center_catalog_editor,
                    provider_editor = asset_center_provider_editor),
    lookups = list(catalog = function() asset_center_catalog(), providers = function() asset_center_provider_catalog(),
                   first_booking = function(asset_ref) asset_center_first_booking(asset_ref), now_utc = function() now_utc(),
                   invalidate_valuation = function() asset_center_valuation_workflow$invalidate(),
                   timeline = asset_center_timeline_reader$overview, timeline_coverage = asset_center_timeline_reader$coverage,
                   valued_series = asset_center_timeline_reader$valued_series),
    context = runtime$context)
  asset_center_valuation_inventory <- function() asset_center_chain$valuation_inventory()
  asset_center_valuation_resolve <- function(rows) asset_center_chain$valuation_resolve(rows)
  asset_center_valuation_workflow <- data_market_valuation_server_v1(input, output, session, asset_center_valuation_service,
    inventory = asset_center_valuation_inventory, resolve_targets = asset_center_valuation_resolve,
    notice=state, selected_asset=function()input$asset_center_asset,
    batch_ref=function() asset_center_batch_workflow$progress()$execution_ref,
    prepare_batch=function(ref) asset_center_batch_workflow$prepare_calendar(ref),
    on_invalidate=function() asset_center_batch_workflow$invalidate())
  asset_center_batch_workflow <- data_market_fx_batch_server_v1(input, output, session, asset_center_batch_service,
    resolve_targets = function(batch) {
      inventory <- data_asset_center_market_inventory_v1(asset_center_catalog(), asset_center_provider_catalog())
      data_market_fx_batch_targets_v1(batch, inventory,
        function(ref) desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", ref),
        function(ref) data_provider_mapping_editor_resolve_history_scope_v1(asset_center_provider_editor, runtime$context, ref),
        function(mapping_id) {
          promotion <- asset_center_provider_promotion_service$recover(mapping_id)
          if (is.null(promotion)) data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
          asset_center_provider_promotion_service$resolve_promotion(promotion$promotion_handle)
        })
    }, now_utc = now_utc, notice = state, on_publication = function() {
      asset_center_valuation_workflow$invalidate()
      asset_center_market_coverage(NULL); asset_center_fx_coverage(NULL); asset_center_completion_plan(NULL)
      asset_center_completion_batch(NULL); asset_center_calendar_gaps(NULL)
    })
  shiny::observeEvent(list(asset_center_catalog(), asset_center_provider_catalog(), asset_center_completion_plan(),
    input$asset_center_coverage_start, input$asset_center_coverage_end, input$asset_center_completion_currency), {
    asset_center_batch_workflow$invalidate()
  }, ignoreNULL = FALSE)
  shiny::observeEvent(input$asset_center_completion_batch_prepare,safe({
    plan<-asset_center_completion_plan();if(is.null(plan)||!identical(plan,prepare_asset_center_completion()))stop("data_asset_center_state_invalid",call.=FALSE)
    batch <- data_asset_center_market_fx_fetch_batch_preview_v1(plan,asset_center_market_coverage(),asset_center_fx_coverage(),now_utc())
    asset_center_batch_workflow$prepare(batch)
    batch
  },function(value){
    asset_center_completion_batch(value)
    state(list(tone=if(identical(value$status,"ready_for_confirmation"))"warning"else"neutral",title="Gemeinsamer Sammelabruf für Kurse und FX geprüft",copy=paste(value$item_count,"Bereiche ·",value$provider_call_count,"Aufrufe beim Kursanbieter ·",value$blocker_count,"Voraussetzungen offen · noch kein Kursabruf · kein Schreiben")))
  }))
  shiny::observeEvent(input$asset_center_completion_asset_action,{
    plan<-asset_center_completion_plan();if(is.null(plan)||is.null(plan$next_action$asset_ref))return()
    asset_center_select(plan$next_action$asset_ref)
    shiny::updateSelectInput(session,"asset_center_market_asset",selected=plan$next_action$asset_ref)
    shiny::updateTabsetPanel(session,"asset_center_step",selected="Marktdaten")
  })
  shiny::observeEvent(input$asset_center_fx_demand, {
    parts <- strsplit(as.character(input$asset_center_fx_demand), "[|]", perl=TRUE)[[1L]]
    if (length(parts)==2L) shiny::updateTextInput(session,"asset_center_fx_query",value=paste(parts[[1L]],parts[[2L]]))
  }, ignoreInit=TRUE)
  shiny::observeEvent(input$asset_center_fx_search_prepare, safe({
    parts <- strsplit(as.character(input$asset_center_fx_demand), "[|]", perl=TRUE)[[1L]]
    if(length(parts)!=2L) stop("asset_center_fx_demand_invalid",call.=FALSE)
    asset_center_fx_search_service$preview("yahoo",trimws(input$asset_center_fx_query),"symbol",now_utc())
  }, function(preview){asset_center_fx_search_preview(preview);asset_center_fx_search_result(NULL);shiny::updateCheckboxInput(session,"asset_center_fx_search_confirm",value=FALSE);state(list(tone="warning",title="FX-Suchabruf bestätigen",copy="Genau eine Yahoo-Suche · kein Schreiben von FX-Paar oder Historie"))}))
  shiny::observeEvent(input$asset_center_fx_search_execute, {
    preview<-asset_center_fx_search_preview();if(is.null(preview)){state(list(tone="error",title="FX-Suche blockiert",copy="Zuerst Suchvorschau erstellen."));return()}
    safe(asset_center_fx_search_service$execute(preview,isTRUE(input$asset_center_fx_search_confirm)),function(result){asset_center_fx_search_result(result);asset_center_fx_search_preview(NULL);shiny::updateCheckboxInput(session,"asset_center_fx_search_confirm",value=FALSE);state(list(tone="neutral",title=paste(result$candidate_count,"FX-Suchvorschläge"),copy="Abruf beim Kursanbieter abgeschlossen · noch kein FX-Paar und keine Historie geschrieben"))})
  })
  shiny::observeEvent(input$asset_center_fx_probe_prepare, safe({
    result<-asset_center_fx_search_result();parts<-strsplit(as.character(input$asset_center_fx_demand),"[|]",perl=TRUE)[[1L]]
    if(is.null(result)||length(parts)!=2L)stop("asset_center_fx_probe_input_invalid",call.=FALSE)
    candidate<-asset_center_fx_search_service$resolve_candidate(input$asset_center_fx_candidate)
    asset_center_fx_probe_service$preview(candidate,parts[[1L]],parts[[2L]],input$asset_center_fx_direction,as.character(input$asset_center_fx_probe_start),as.character(input$asset_center_fx_probe_end),now_utc())
  },function(preview){asset_center_fx_probe_preview(preview);asset_center_fx_probe_result(NULL);shiny::updateCheckboxInput(session,"asset_center_fx_probe_confirm",value=FALSE);state(list(tone="warning",title="FX-Testabruf bestätigen",copy="Genau ein Yahoo-Abruf · nur lokal beim Eigentümer vorgemerkt · noch kein Schreiben der FX-Historie"))}))
  shiny::observeEvent(input$asset_center_fx_probe_execute,{
    preview<-asset_center_fx_probe_preview();if(is.null(preview)){state(list(tone="error",title="FX-Test blockiert",copy="Zuerst Testabruf-Vorschau erstellen."));return()}
    safe(asset_center_fx_probe_service$execute(preview,isTRUE(input$asset_center_fx_probe_confirm)),function(result){asset_center_fx_probe_result(result);asset_center_fx_probe_preview(NULL);shiny::updateCheckboxInput(session,"asset_center_fx_probe_confirm",value=FALSE);state(list(tone="positive",title="FX-Testnachweis lokal beim Eigentümer vorgemerkt",copy=paste(result$observed_day_count,"Beobachtungen ·",result$source_gap_day_count,"Quelllücken · noch kein Schreiben von FX-Paar oder Historie")))})
  })
  shiny::observeEvent(input$asset_center_fx_promotion_prepare,safe({
    probe<-asset_center_fx_probe_result();if(is.null(probe)||is.null(probe$result_ref))stop("asset_center_fx_probe_required",call.=FALSE)
    asset_center_fx_promotion_service$preview(asset_center_fx_probe_service$resolve_result(probe$result_ref),now_utc())
  },function(preview){asset_center_fx_promotion_preview(preview);asset_center_fx_promotion_result(NULL);shiny::updateCheckboxInput(session,"asset_center_fx_promotion_confirm",value=FALSE);state(list(tone="warning",title="FX-Paar und Testhistorie bestätigen",copy="Nur fortgeschriebenes Schreiben (Schema 2600) · kein erneuter Abruf beim Kursanbieter"))}))
  shiny::observeEvent(input$asset_center_fx_promotion_execute,{
    preview<-asset_center_fx_promotion_preview();if(is.null(preview)){state(list(tone="error",title="Freigabe des Devisenpaars blockiert",copy="Zuerst die Vorschau der Freigabe erstellen."));return()}
    safe(asset_center_fx_promotion_service$publish(preview,isTRUE(input$asset_center_fx_promotion_confirm),now_utc()),function(result){asset_center_fx_promotion_result(result);asset_center_fx_promotion_preview(NULL);shiny::updateCheckboxInput(session,"asset_center_fx_promotion_confirm",value=FALSE);state(list(tone="positive",title="FX-Paar und Testhistorie veröffentlicht",copy=paste(result$appended_day_count,"neu ·",result$corrected_day_count,"korrigiert · kein erneuter Abruf beim Kursanbieter")))})
  })
  asset_center_fx_invalidate <- function(plan=TRUE) {
    asset_center_fx_history_service$invalidate()
    if(plan)asset_center_fx_history_plan(NULL)
    asset_center_fx_history_preview(NULL);asset_center_fx_history_review(NULL);asset_center_fx_attempts(NULL)
    for(id in c('asset_center_fx_history_fetch_confirm','asset_center_fx_history_publish_confirm','asset_center_fx_attempt_ack'))shiny::updateCheckboxInput(session,id,value=FALSE)
  }
  shiny::observeEvent(list(input$asset_center_fx_demand,input$asset_center_fx_history_start,input$asset_center_fx_history_end),{
    asset_center_fx_invalidate()
  },ignoreInit=TRUE,priority=100)
  shiny::observeEvent(input$asset_center_fx_history_range,{
    asset_center_fx_invalidate(FALSE)
  },ignoreInit=TRUE,priority=100)
  shiny::observeEvent(input$asset_center_fx_attempts_read,safe({
    asset_center_fx_invalidate(FALSE);asset_center_fx_history_service$inspect()
  },function(value){asset_center_fx_attempts(value)}))
  shiny::observeEvent(input$asset_center_fx_attempt_recover,safe({
    parts<-strsplit(as.character(input$asset_center_fx_demand),'[|]',perl=TRUE)[[1L]];if(length(parts)!=2L)stop('asset_center_fx_demand_invalid',call.=FALSE)
    asset_center_fx_history_service$recover(input$asset_center_fx_attempt_ref,parts[[1L]],parts[[2L]],as.character(input$asset_center_fx_history_start),as.character(input$asset_center_fx_history_end))
  },function(value){asset_center_fx_history_review(value);asset_center_fx_attempts(NULL);state(list(tone='positive',title='Gespeicherten FX-Kandidaten geladen',copy='Kein Abruf · Veröffentlichung separat bestätigen.'))}))
  shiny::observeEvent(input$asset_center_fx_attempt_review,safe({
    asset_center_fx_history_service$acknowledge(input$asset_center_fx_attempt_ref,isTRUE(input$asset_center_fx_attempt_ack))
  },function(value){asset_center_fx_invalidate(FALSE);state(list(tone='neutral',title='Versuch ohne gespeichertes Ergebnis geprüft',copy='Kein Beweis eines ausgebliebenen Netzwerkabrufs. Alter Versuch bleibt erhalten; kein neuer Abruf. Weitere Versuche einzeln lesen und prüfen.'))}))
  shiny::observeEvent(input$asset_center_fx_history_plan_action,safe({
    asset_center_fx_invalidate()
    parts<-strsplit(as.character(input$asset_center_fx_demand),"[|]",perl=TRUE)[[1L]];if(length(parts)!=2L)stop("asset_center_fx_history_input_invalid",call.=FALSE)
    asset_center_fx_history_service$plan(parts[[1L]],parts[[2L]],as.character(input$asset_center_fx_history_start),as.character(input$asset_center_fx_history_end))
  },function(plan){asset_center_fx_history_plan(plan);asset_center_fx_history_preview(NULL);asset_center_fx_history_review(NULL);state(list(tone=if(plan$target_day_count>0L)"warning"else"positive",title=paste(plan$target_day_count,"fehlende FX-Tage"),copy="Planung nur lesend · kein Kursabruf · kein Schreiben"))}))
  shiny::observeEvent(input$asset_center_fx_history_preview_action,safe({
    asset_center_fx_invalidate(FALSE)
    plan<-asset_center_fx_history_plan();rows<-Filter(function(row)identical(row$range_ref,input$asset_center_fx_history_range),plan$ranges);if(length(rows)!=1L)stop("asset_center_fx_history_range_invalid",call.=FALSE);parts<-strsplit(as.character(input$asset_center_fx_demand),"[|]",perl=TRUE)[[1L]]
    asset_center_fx_history_service$preview(parts[[1L]],parts[[2L]],rows[[1L]]$start_date,rows[[1L]]$end_date,now_utc())
  },function(preview){asset_center_fx_history_preview(preview);asset_center_fx_history_review(NULL);shiny::updateCheckboxInput(session,"asset_center_fx_history_fetch_confirm",value=FALSE);state(list(tone="warning",title="FX-Abruf bestätigen",copy="Genau ein Bereich · genau ein Yahoo-Abruf · nur lokal beim Eigentümer vorgemerkt"))}))
  shiny::observeEvent(input$asset_center_fx_history_stage_action,{
    preview<-asset_center_fx_history_preview();if(is.null(preview)){state(list(tone="error",title="FX-Abruf blockiert",copy="Zuerst Abrufvorschau erstellen. Nach einem Fehler: gespeicherte FX-Versuche lesen, nicht wiederholen."));return()}
    confirmed<-isTRUE(input$asset_center_fx_history_fetch_confirm)
    if(!confirmed){state(list(tone='warning',title='Bestätigung fehlt',copy='Genau diesen FX-Abruf bestätigen.'));return()}
    asset_center_fx_history_preview(NULL);asset_center_fx_history_review(NULL);shiny::updateCheckboxInput(session,'asset_center_fx_history_fetch_confirm',value=FALSE)
    safe(asset_center_fx_history_service$stage(preview,confirmed),function(review){asset_center_fx_history_review(review);asset_center_fx_history_preview(NULL);shiny::updateCheckboxInput(session,"asset_center_fx_history_fetch_confirm",value=FALSE);state(list(tone="positive",title="FX-Kandidat lokal beim Eigentümer vorgemerkt",copy=paste(review$observed_day_count,"beobachtet ·",review$source_gap_day_count,"Quelllücken · noch nichts in die Devisenkurshistorie geschrieben")))})
  })
  shiny::observeEvent(input$asset_center_fx_history_publish,{
    review<-asset_center_fx_history_review();if(is.null(review)){state(list(tone="error",title="FX-Publication blockiert",copy="Kein gestagter Kandidat."));return()}
    confirmed<-isTRUE(input$asset_center_fx_history_publish_confirm)
    if(!confirmed)return()
    asset_center_fx_history_review(NULL);shiny::updateCheckboxInput(session,'asset_center_fx_history_publish_confirm',value=FALSE)
    safe(asset_center_fx_history_service$publish(review,confirmed,now_utc()),function(result){asset_center_fx_history_publication(result);asset_center_fx_history_review(NULL);asset_center_valuation_workflow$invalidate();asset_center_fx_coverage(NULL);shiny::updateCheckboxInput(session,"asset_center_fx_history_publish_confirm",value=FALSE);state(list(tone="positive",title="FX-Historie veröffentlicht",copy=paste(result$appended_day_count,"neu · kein erneuter Abruf beim Kursanbieter")))})
  })
  calendar_report <- function(value) { asset_center_calendar_feedback(value); state(value) }
  calendar_safe <- function(expression, success) tryCatch(
    .desktop_product_force_before_success_v1(expression,success),error=function(error) {
      asset_center_calendar_review_service$invalidate()
      asset_center_calendar_binding_preview(NULL);asset_center_calendar_correction_preview(NULL);asset_center_calendar_batch_preview(NULL)
      for(id in c('asset_center_calendar_binding_confirm','asset_center_calendar_correction_confirm','asset_center_calendar_batch_confirm'))shiny::updateCheckboxInput(session,id,value=FALSE)
      calendar_report(list(tone='error',title='Kalenderaktion nicht abgeschlossen',copy=paste(pl_error_text_v1(spotcore::desktop_product_safe_error_code_v1(error)),'Nicht blind wiederholen, sondern zuerst die gespeicherte Abdeckung prüfen.')))
    })
  calendar_after_write <- function(value) {
    refreshed<-tryCatch({accept_asset_center_coverage(read_asset_center_coverage());TRUE},error=function(e)FALSE)
    if(!refreshed){value$tone<-'warning';value$copy<-paste(value$copy,'· Speicherung erfolgreich, Aktualisierung der Abdeckung fehlgeschlagen. Nur lesend erneut prüfen, nicht erneut schreiben.')}
    calendar_report(value)
  }
  asset_center_calendar_target <- function() {
    gaps<-asset_center_calendar_gaps();key<-input$asset_center_calendar_scope
    if(is.null(gaps)||!identical(gaps$start_date,as.character(input$asset_center_coverage_start))||!identical(gaps$end_date,as.character(input$asset_center_coverage_end))||is.null(key)||!nzchar(key))stop('desktop_calendar_gap_review_input_invalid',call.=FALSE)
    target<-asset_center_calendar_targets()[[key]]
    if(is.null(target))stop('desktop_calendar_gap_review_input_invalid',call.=FALSE)
    target
  }
  shiny::observeEvent(list(input$asset_center_calendar_scope,input$asset_center_calendar_closures,
    input$asset_center_calendar_correction_date,input$asset_center_coverage_start,input$asset_center_coverage_end), {
    asset_center_calendar_review_service$invalidate()
    asset_center_calendar_binding_preview(NULL);asset_center_calendar_correction_preview(NULL);asset_center_calendar_batch_preview(NULL)
    for(id in c('asset_center_calendar_binding_confirm','asset_center_calendar_correction_confirm','asset_center_calendar_batch_confirm'))shiny::updateCheckboxInput(session,id,value=FALSE)
  },ignoreInit=TRUE,priority=100)
  shiny::observeEvent(input$asset_center_calendar_select_proposals, {
    target<-tryCatch(asset_center_calendar_target(),error=function(e)NULL);if(is.null(target))return()
    if(!identical(target$kind,'listing'))return() # FX always needs its own manual evidence.
    dates<-data_calendar_binding_choices_v1(asset_center_calendar_gaps()$rows,target)
    shiny::updateCheckboxGroupInput(session,'asset_center_calendar_closures',selected=dates)
  })
  shiny::observeEvent(input$asset_center_calendar_binding_prepare, calendar_safe({
    target<-asset_center_calendar_target()
    dates<-input$asset_center_calendar_closures;if(is.null(dates)||!length(dates))stop('desktop_calendar_gap_review_input_invalid',call.=FALSE)
    if(target$kind=='listing')asset_center_calendar_review_service$preview_listing_binding(target$listing_ref,dates,as.character(input$asset_center_coverage_start),as.character(input$asset_center_coverage_end),now_utc())
    else asset_center_calendar_review_service$preview_binding(target$source,target$target,dates,as.character(input$asset_center_coverage_start),as.character(input$asset_center_coverage_end),now_utc())
  }, function(p) {
    asset_center_calendar_binding_preview(p)
    shiny::updateCheckboxInput(session,'asset_center_calendar_binding_confirm',value=FALSE)
    calendar_report(list(tone='warning',title='Kalenderprofil-Bindung bestätigen',copy=paste(p$retained_closure_count,'Schließtage beibehalten ·',p$added_closure_count,'neu ·',p$closure_count,'gesamt · keine Tage entfernt · vollständige Vorschau unten prüfen · kein Schreiben von Kursanbieter- oder Historiendaten')))
  }))
  shiny::observeEvent(input$asset_center_calendar_binding_apply, {
    p<-asset_center_calendar_binding_preview();if(is.null(p))return()
    calendar_safe(
      asset_center_calendar_review_service$apply_binding(p,isTRUE(input$asset_center_calendar_binding_confirm),now_utc()),
      function(r) {
        asset_center_calendar_binding_preview(NULL)
        calendar_after_write(list(tone='positive',title='Kalenderprofil ausdrücklich gebunden',copy='Kalender des ausgewählten Bereichs gebunden; bestehende bestätigte Entscheidungen erhalten · noch keine Korrektur der Historie · andere Altbindungen unverändert'))
      }
    )
  })
  shiny::observeEvent(input$asset_center_calendar_correction_prepare, calendar_safe({
    target<-asset_center_calendar_target()
    if(target$kind=='listing')asset_center_calendar_review_service$preview_listing_correction(target$listing_ref,input$asset_center_calendar_correction_date,now_utc())
    else asset_center_calendar_review_service$preview_correction(target$source,target$target,input$asset_center_calendar_correction_date,now_utc())
  }, function(p) {
    asset_center_calendar_correction_preview(p)
    shiny::updateCheckboxInput(session,'asset_center_calendar_correction_confirm',value=FALSE)
    calendar_report(list(tone='warning',title='Kalenderkorrektur bestätigen',copy='Genau ein source_gap → non_trading_day · kein Kurs wird erfunden'))
  }))
  shiny::observeEvent(input$asset_center_calendar_correction_apply, {
    p<-asset_center_calendar_correction_preview();if(is.null(p))return()
    calendar_safe(
      asset_center_calendar_review_service$apply_correction(p,isTRUE(input$asset_center_calendar_correction_confirm),now_utc()),
      function(r) {
        asset_center_calendar_correction_preview(NULL)
        calendar_after_write(list(tone='positive',title='Kalenderkorrektur veröffentlicht',copy=paste(r$date,'· nur fortgeschrieben · kein Kursabruf')))
      }
    )
  })
  shiny::observeEvent(input$asset_center_calendar_batch_prepare, calendar_safe({
    asset_center_calendar_review_service$invalidate();asset_center_calendar_batch_preview(NULL)
    asset_center_calendar_binding_preview(NULL);asset_center_calendar_correction_preview(NULL)
    target<-asset_center_calendar_target()
    if(target$kind!='listing')stop('desktop_calendar_gap_review_input_invalid',call.=FALSE)
    rows<-Filter(function(r)r$scope_kind=='listing'&&r$consumer_ref==target$consumer&&r$disposition=='calendar_correction_proposed',asset_center_calendar_gaps()$rows)
    dates<-vapply(rows,`[[`,character(1L),'date')
    asset_center_calendar_review_service$preview_batch(target$listing_ref,dates,now_utc())
  },function(p){
    asset_center_calendar_batch_preview(p);shiny::updateCheckboxInput(session,'asset_center_calendar_batch_confirm',value=FALSE)
    calendar_report(list(tone='warning',title='Sammelkorrektur prüfen',copy=paste(p$day_count,'ausdrücklich gewählte Tage für genau die ausgewählte Notierung · eine atomare Korrektur · noch kein Schreiben')))
  }))
  shiny::observeEvent(input$asset_center_calendar_batch_apply, {
    p<-asset_center_calendar_batch_preview();if(is.null(p))return()
    if(!isTRUE(input$asset_center_calendar_batch_confirm)){calendar_report(list(tone='warning',title='Bestätigung fehlt',copy='Zuerst alle angezeigten Tage prüfen und genau diese Sammelkorrektur bestätigen.'));return()}
    asset_center_calendar_batch_preview(NULL);shiny::updateCheckboxInput(session,'asset_center_calendar_batch_confirm',value=FALSE)
    calendar_safe(asset_center_calendar_review_service$apply_batch(p,TRUE,now_utc()),function(r){
      calendar_after_write(list(tone='positive',title='Sammelkorrektur veröffentlicht',copy=paste(r$corrected_day_count,'Tage ·',head(unlist(r$dates),1),'bis',tail(unlist(r$dates),1),'· atomar und nur fortgeschrieben · kein Kursabruf · nicht ausgewählte Tage unverändert')))
    })
  })
  shiny::observeEvent(input$asset_center_market_continue, safe({
    catalog <- asset_center_catalog(); providers <- asset_center_provider_catalog()
    if (is.null(catalog) || is.null(providers)) stop("asset_center_refresh_required", call. = FALSE)
    inventory <- data_asset_center_market_inventory_v1(catalog, providers)
    rows <- Filter(function(row) identical(row$asset_ref, input$asset_center_market_asset), inventory$rows)
    if (length(rows) != 1L) stop("asset_center_market_selection_invalid", call. = FALSE)
    row <- rows[[1L]]
    shiny::updateRadioButtons(session, "asset_center_mode", selected = "existing")
    asset_center_select(row$asset_ref)
    if (identical(row$status, "mapping_missing")) {
      selected <- data_asset_center_selected_v1(catalog, row$asset_ref)
      query <- if (!is.null(selected$isin) && nzchar(selected$isin)) selected$isin else selected$display_name
      shiny::updateTextInput(session, "asset_center_provider_query", value = query)
      shiny::updateSelectInput(session, "asset_center_search_provider", selected = "yahoo")
      shiny::updateSelectInput(session, "asset_center_provider_search_mode", selected = if (!is.null(selected$isin) && nzchar(selected$isin)) "isin" else "name")
      shiny::updateTabsetPanel(session, "asset_center_step", selected = "Marktdaten")
    } else if (identical(row$status, "history_ready_to_plan")) {
      matching <- Filter(function(mapping) identical(mapping$asset_ref, row$asset_ref) &&
        identical(mapping$capability, "daily_history") && isTRUE(mapping$enabled) &&
        identical(mapping$verification_status, "verified") && identical(mapping$provider_currency, row$price_currency),
        providers$mappings)
      if (length(matching)) shiny::updateSelectInput(session, "asset_center_mapping", selected = matching[[1L]]$ref)
      coverage <- asset_center_market_coverage()
      coverage_rows <- if (is.null(coverage)) list() else Filter(function(item) identical(item$asset_ref, row$asset_ref), coverage$rows)
      if (length(coverage_rows) == 1L && length(coverage_rows[[1L]]$missing_ranges)) {
        range <- coverage_rows[[1L]]$missing_ranges[[1L]]
        shiny::updateDateInput(session, "asset_center_history_start", value = as.Date(range$start_date))
        shiny::updateDateInput(session, "asset_center_history_end", value = as.Date(range$end_date))
        shiny::updateSelectInput(session, "asset_center_history_mode", selected = "incremental")
        row$next_step <- paste("Fehlenden Zeitraum", range$start_date, "bis", range$end_date, "planen")
      }
      shiny::updateTabsetPanel(session, "asset_center_step", selected = "Marktdaten")
    } else {
      matching <- Filter(function(mapping) identical(mapping$asset_ref, row$asset_ref) && identical(mapping$capability, "daily_history"), providers$mappings)
      if (length(matching)) shiny::updateSelectInput(session, "asset_center_mapping", selected = matching[[1L]]$ref)
      shiny::updateTabsetPanel(session, "asset_center_step", selected = "Marktdaten")
    }
    row
  }, function(value) {
    state(list(tone = "neutral", title = value$status_label, copy = paste(value$asset_name, "·", value$next_step, "· kein Kursabruf")))
  }))
  shiny::observeEvent(input$asset_center_provider_refresh, safe(asset_center_refresh(), function(value) {
    state(list(tone = "neutral", title = "Kurszuordnungen gelesen", copy = "Es wurde kein Kursanbieter kontaktiert."))
  }))
  shiny::observeEvent(input$asset_center_mapping, {
    model <- asset_center_provider_catalog(); ref <- input$asset_center_mapping
    if (is.null(model) || is.null(ref) || !nzchar(ref)) return(invisible(NULL))
    rows <- Filter(function(row) identical(row$ref, ref), model$mappings)
    if (length(rows) != 1L || !identical(rows[[1L]]$asset_ref, input$asset_center_asset)) return(invisible(NULL)); row <- rows[[1L]]
    asset_center_reset_confirmations()
    asset_center_defaults_notice("Gespeicherte Zuordnung · kein USD-Ersatz und keine Übernahme aus einem anderen Asset.")
    shiny::updateSelectInput(session, "asset_center_provider_capability", selected = row$capability)
    asset_center_select_provider(row$provider_id)
    shiny::updateTextInput(session, "asset_center_provider_symbol", value = row$provider_symbol)
    shiny::updateTextInput(session, "asset_center_provider_exchange", value = if (is.null(row$exchange_code)) "" else row$exchange_code)
    shiny::updateTextInput(session, "asset_center_provider_mic", value = if (is.null(row$mic_code)) "" else row$mic_code)
    asset_center_currency_auto_value <<- row$provider_currency
    shiny::updateTextInput(session, "asset_center_provider_currency", value = row$provider_currency)
    shiny::updateCheckboxInput(session, "asset_center_provider_expert", value = isTRUE(row$expert_only))
    asset_center_provider_probe_result(NULL); asset_center_provider_promotion_result(NULL); asset_center_market_plan(NULL)
    asset_center_market_fetch_preview(NULL); asset_center_market_fetch_result(NULL)
    asset_center_market_review(NULL); asset_center_market_publication_result(NULL)
    scope <- tryCatch({
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      if (identical(row$verification_status, "verified")) data_provider_mapping_editor_resolve_history_scope_v1(asset_center_provider_editor, runtime$context, ref)
      else if (identical(row$verification_status, "unverified")) data_provider_mapping_editor_resolve_probe_scope_v1(asset_center_provider_editor, runtime$context, ref)
      else NULL
    }, error = function(error) NULL)
    if (!is.null(scope) && identical(row$verification_status, "unverified")) {
      probe_scope <- scope; probe_scope$catalog_fingerprint <- NULL
      recovered_probe <- tryCatch(asset_center_provider_probe_service$recover(probe_scope), error = function(error) NULL)
      if (!is.null(recovered_probe)) {
        asset_center_provider_probe_result(recovered_probe)
        shiny::updateTextInput(session, "asset_center_listing_timezone", value = recovered_probe$timezone_name)
      }
    }
    if (!is.null(scope)) {
      recovered_promotion <- tryCatch(asset_center_provider_promotion_service$recover(scope$mapping_id), error = function(error) NULL)
      if (!is.null(recovered_promotion)) {
        promotion_private <- tryCatch(asset_center_provider_promotion_service$resolve_promotion(recovered_promotion$promotion_handle), error = function(error) NULL)
        promotion_matches <- !is.null(promotion_private) && identical(promotion_private$mapping_id, scope$mapping_id) && (
          identical(promotion_private$mapping_fingerprint, scope$mapping_fingerprint) ||
            identical(row$verification_status, "verified") && scope$mapping_revision == promotion_private$mapping_revision + 1L
        )
        if (isTRUE(promotion_matches)) {
          asset_center_provider_promotion_result(recovered_promotion)
          asset_center_history_state(if (recovered_promotion$source_gap_day_count > 0L) "source_gap" else "partial")
        }
      }
    }
  }, ignoreInit = TRUE)
  shiny::observeEvent(list(input$asset_center_provider_action, input$asset_center_mapping,
    input$asset_center_provider_capability, input$asset_center_provider_id, input$asset_center_provider_symbol,
    input$asset_center_provider_exchange, input$asset_center_provider_mic, input$asset_center_provider_currency,
    input$asset_center_provider_expert), {
      asset_center_provider_preview(NULL); action_feedback$clear('mapping')
      shiny::updateCheckboxInput(session, "asset_center_provider_confirm", value = FALSE)
  }, ignoreInit = TRUE, priority = 100)
  shiny::observeEvent(list(input$asset_center_provider_query, input$asset_center_search_provider, input$asset_center_provider_search_mode), {
    asset_center_provider_search_preview(NULL); asset_center_provider_search_result(NULL)
    action_feedback$clear(c('search','candidate'))
    shiny::updateSelectInput(session, 'asset_center_provider_candidate', choices=c('Noch keine Vorschläge'=''),selected='')
    shiny::updateCheckboxInput(session, "asset_center_provider_search_confirm", value = FALSE)
  }, ignoreInit = TRUE, priority = 100)
  shiny::observeEvent(list(input$asset_center_mode, input$asset_center_mapping), {
    asset_center_provider_probe_preview(NULL); asset_center_provider_promotion_preview(NULL)
    asset_center_mapping_verify_preview(NULL); asset_center_market_fetch_preview(NULL); asset_center_market_review(NULL)
    for (suffix in c("provider_probe", "promotion", "mapping_verify", "history_fetch", "history_publish", "history_reject"))
      shiny::updateCheckboxInput(session, paste0("asset_center_", suffix, "_confirm"), value = FALSE)
  }, ignoreInit = TRUE, priority = 100)
  action_feedback$observe('mapping', input$asset_center_provider_prepare, safe(
    data_provider_mapping_editor_prepare_v1(asset_center_provider_editor, runtime$context, asset_center_provider_form(), now_utc()),
    function(preview) {
      asset_center_provider_preview(preview); shiny::updateCheckboxInput(session, "asset_center_provider_confirm", value = FALSE)
      state(list(tone = "neutral", title = "Kurszuordnung geprüft", copy = "Die Zuordnung bleibt ohne Testabruf ungeprüft und deaktiviert."))
    }
  ))
  action_feedback$observe('mapping', input$asset_center_provider_execute, {
    preview <- asset_center_provider_preview()
    if (is.null(preview)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("data_provider_mapping_preview_required"))); return()
    }
    safe({
      asset_center_require_market(!identical(preview$action, "create"))
      data_provider_mapping_editor_execute_v1(asset_center_provider_editor, runtime$context, preview, isTRUE(input$asset_center_provider_confirm))
    },
      function(result) {
        invisible(asset_center_refresh(input$asset_center_asset)); asset_center_provider_preview(NULL)
        shiny::updateCheckboxInput(session, "asset_center_provider_confirm", value = FALSE)
        state(list(tone = "positive", title = "Kurszuordnung gespeichert", copy = if(identical(preview$action,'disable')) 'Die Zuordnung ist deaktiviert. Vorhandene Historie bleibt erhalten.' else 'Die Zuordnung ist noch nicht verifiziert und bleibt deaktiviert. Testdaten und Aktivierung erfordern eigene Prüfungen und Bestätigungen.'))
        if (identical(preview$action, "create")) provider_worklist$mapping_saved()
      }
    )
  })
  output$asset_center_search_master <- shiny::renderUI({
    if (!identical(input$asset_center_mode,"new")) return(NULL)
    prefill <- shiny::isolate(asset_center_new_prefill())
    providers <- shiny::isolate(asset_center_search_providers())
    if (is.null(prefill)) data_asset_center_search_ui_v1(providers = providers) else data_asset_center_search_ui_v1(data_asset_center_prefill_query_v1(prefill), data_asset_center_prefill_mode_v1(prefill), providers)
  })
  # Suchanbieter (rc.392, #495): aktive Kursanbieter mit Suche. Gelesen aus dem Reiter Kursanbieter, sonst einmal ueber den Dienst;
  # schaltet der Nutzer dort einen Anbieter ein, steht er hier ohne Neuladen zur Wahl.
  asset_center_price_provider_rows <- shiny::reactive({
    current <- price_providers$overview()
    if (is.null(current) || !is.null(attr(current, "code")))
      current <- if (is.null(price_providers_service)) NULL else tryCatch(price_providers_service$overview(), error = function(error) NULL)
    if (is.list(current)) current$providers else NULL
  })
  asset_center_search_providers <- shiny::reactive(data_asset_center_search_providers_v1(asset_center_price_provider_rows()))
  # Anbieter der Kurszuordnung (rc.394, #495): Yahoo als Vorgabe, dazu aktive Anbieter mit Tageskursen. Die gewaehlte Angabe bleibt.
  shiny::observeEvent(asset_center_price_provider_rows(), {
    current <- input$asset_center_provider_id
    choices <- data_asset_center_history_providers_v1(asset_center_price_provider_rows(), current)
    shiny::updateSelectInput(session, "asset_center_provider_id", choices = choices,
                             selected = if (isTRUE(current %in% choices)) current else "yahoo")
  })
  # Was der gewaehlte Anbieter nicht leistet (bei EODHD: keine Splits), steht direkt unter der Auswahl.
  output$asset_center_provider_note <- shiny::renderUI({
    note <- pl_price_provider_note_v1(input$asset_center_provider_id)
    if (is.null(note)) NULL else portelyra_status_panel("Hinweis zu diesem Kursanbieter", note, tone = "warning")
  })
  shiny::observeEvent(asset_center_search_providers(), {
    choices <- asset_center_search_providers()
    current <- input$asset_center_search_provider
    shiny::updateSelectInput(session, "asset_center_search_provider", choices = choices, selected = if (isTRUE(current %in% choices)) current else "yahoo")
  }, ignoreInit = TRUE)
  output$asset_center_search_market <- shiny::renderUI({
    if (identical(input$asset_center_mode,"new")) return(NULL)
    asset<-asset_center_selected();if(is.null(asset))return(NULL)
    isin<-if(is.null(asset$isin))""else asset$isin
    data_asset_center_search_ui_v1(if(nzchar(isin))isin else asset$display_name,if(nzchar(isin))"isin"else"name",shiny::isolate(asset_center_search_providers()))
  })
  output$asset_center_market_selection_notice <- shiny::renderUI({
    asset<-asset_center_selected();if(is.null(asset))return(NULL)
    shiny::p(class = "pl-field-hint", shiny::strong(paste("Kursquelle und Bewertung für:",asset$display_name)),
      " · Der Name muss nicht dem Namen beim Anbieter entsprechen.")
  })
  shiny::observeEvent(input$asset_center_mode, {
    asset_center_provider_search_preview(NULL); asset_center_provider_search_result(NULL)
    shiny::updateCheckboxInput(session, "asset_center_provider_search_confirm", value = FALSE)
    if (identical(input$asset_center_mode, "new")) {
      shiny::updateTabsetPanel(session, "asset_center_step", selected = "1 · Stammdaten"); shiny::updateTabsetPanel(session, "master_section", selected = "assets")
      shiny::updateSelectInput(session, "asset_center_provider_candidate", choices = c("Noch keine Vorschläge" = ""), selected = "")
      prefill <- asset_center_new_prefill()
      if (is.null(prefill)) {
        shiny::updateTextInput(session, "asset_center_provider_query", value = "")
        shiny::updateSelectInput(session, "asset_center_provider_search_mode", selected = "name")
      } else asset_center_prefill_fields(prefill)
    } else {
      # Wer selbst zurueck auf "Bestehendes Asset" stellt, bricht die Neuanlage aus dem Import ab.
      asset_center_new_prefill(NULL)
    }
  }, ignoreInit = TRUE, priority = 100)
  action_feedback$observe('search', input$asset_center_provider_search, safe({
    action_feedback$clear(c('search','candidate'))
    asset_center_require_search()
    # Wird der Suchblock gerade neu aufgebaut, sind Anbieter und Modus noch leer;
    # ein leerer Suchtext ist eine Eingabe, kein Systemfehler. Beides wurde bisher
    # zum Sammelcode desktop_provider_search_input_invalid (23.09.2026, #283).
    text <- function(value, fallback) if (is.character(value) && length(value) == 1L && nzchar(trimws(value))) trimws(value) else fallback
    query <- text(input$asset_center_provider_query, "")
    if (!nzchar(query)) stop("asset_center_search_query_required", call. = FALSE)
    asset_center_provider_search_service$preview(
      text(input$asset_center_search_provider, "yahoo"), query,
      text(input$asset_center_provider_search_mode, "name"), now_utc()
    )
  },
    function(preview) {
      asset_center_provider_search_preview(preview); asset_center_provider_search_result(NULL)
      shiny::updateCheckboxInput(session, "asset_center_provider_search_confirm", value = FALSE)
      shiny::updateSelectInput(session, "asset_center_provider_candidate", choices = c("Noch keine Vorschläge" = ""), selected = "")
      asset_center_provider_online(list(
        tone = "warning", title = "Ein Providerabruf wartet auf Bestätigung",
        copy = "Noch erfolgte kein Netzwerkzugriff. Der sichtbare Suchtext und genau ein Versuch beim gewählten Suchanbieter sind gebunden."
      ))
    }
  ))
  action_feedback$observe('search', input$asset_center_provider_search_execute, {
    action_feedback$clear('search')
    preview <- asset_center_provider_search_preview()
    if (is.null(preview)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("data_provider_search_preview_required"))); return()
    }
    safe({ asset_center_require_search(); asset_center_provider_search_service$execute(preview, isTRUE(input$asset_center_provider_search_confirm)) }, function(result) {
      asset_center_provider_search_result(result); asset_center_provider_search_preview(NULL)
      shiny::updateCheckboxInput(session, "asset_center_provider_search_confirm", value = FALSE)
      choices <- if (!length(result$candidates)) c("Keine Vorschläge" = "") else stats::setNames(
        vapply(result$candidates, `[[`, character(1L), "ref"),
        vapply(result$candidates, function(row) paste(row$display_name, "·", row$symbol, "·", row$exchange, "·", if (is.null(row$quote_currency)) "Währung offen" else row$quote_currency,
          "· ISIN", if (is.null(row$isin)) "nicht geliefert" else row$isin), character(1L))
      )
      shiny::updateSelectInput(session, "asset_center_provider_candidate", choices = choices, selected = if (length(result$candidates)) result$candidates[[1L]]$ref else "")
      asset_center_provider_online(list(
        tone = if (length(result$candidates)) "positive" else "warning",
        title = paste(length(result$candidates), "Vorschläge vom Kursanbieter empfangen"),
        copy = "Kein Vorschlag wurde automatisch übernommen; Stammdaten, Steuer und Kurshistorie wurden nicht geschrieben."
      ))
    })
  })
  action_feedback$observe('candidate', input$asset_center_provider_candidate_apply, {
    handle <- input$asset_center_provider_candidate
    candidate <- tryCatch(asset_center_provider_search_service$resolve_candidate(handle), error = function(error) NULL)
    result <- asset_center_provider_search_result()
    if (is.null(candidate) || is.null(result) || !any(vapply(result$candidates, function(r) identical(r$ref, handle), logical(1L)))) {
      state(list(tone = "error", title = "Vorschlag nicht übernommen", copy = "Der Vorschlag gehört nicht zur aktuellen Suche. Bitte erneut suchen und einen Vorschlag wählen."))
      return()
    }
    if (identical(input$asset_center_mode, "new")) {
      # Explicit candidate selection fills only an uncommitted master form.
      fields <- data_asset_center_candidate_master_v1(candidate, input$asset_center_isin)
      shiny::updateTextInput(session, "asset_center_name", value = fields$display_name)
      shiny::updateTextInput(session, "asset_center_isin", value = fields$isin)
      # Ein Vorschlag ohne Waehrung (Yahoo liefert bei der Suche keine) laesst die eingetragene Kurswaehrung stehen (#447).
      if (nzchar(fields$price_currency)) shiny::updateTextInput(session, "asset_center_currency", value = fields$price_currency)
      if (!is.null(fields$asset_type)) {
        shiny::updateRadioButtons(session, "asset_center_domain", selected = if (identical(fields$asset_type, "cash")) "cash" else "non_cash")
        shiny::updateSelectInput(session, "asset_center_type", selected = fields$asset_type)
      }
      asset_center_core_preview(NULL); shiny::updateCheckboxInput(session, "asset_center_core_confirm", value = FALSE)
      state(list(tone="neutral", title="Stammdaten-Vorschlag übernommen", copy="Name, Typ und gelieferte Währung sind editierbare Vorschläge. ISIN nur soweit geliefert; keine Anlage, keine Kurszuordnung und kein Kursabruf."))
      return()
    }
    defaults <- data_market_defaults_v1(asset_center_selected(), candidate = candidate,
                                        provider = if (is.character(result$provider_id)) result$provider_id else "yahoo")
    asset_center_apply_provider_draft(defaults)
    shiny::updateCheckboxInput(session, "asset_center_provider_expert", value = FALSE)
    asset_center_defaults_notice(paste(defaults$currency_basis, "· noch nicht gespeichert/verifiziert."))
    if (identical(input$asset_center_mode, "new") && !nzchar(input$asset_center_name)) shiny::updateTextInput(session, "asset_center_name", value = candidate$display_name)
    # Falscher Ticker (#456): Der Vorschlag wird zum Entwurf "Zuordnung korrigieren" der gespeicherten Zuordnung. Je Asset,
    # Verwendung und Provider gibt es genau eine; gespeichert wird erst nach Pruefen und Bestaetigen, danach "Jetzt einrichten".
    stored <- is.character(input$asset_center_mapping) && length(input$asset_center_mapping) == 1L && nzchar(input$asset_center_mapping)
    asset_center_provider_preview(NULL); shiny::updateCheckboxInput(session, "asset_center_provider_confirm", value = FALSE)
    if (stored) {
      shiny::updateSelectInput(session, "asset_center_provider_action", selected = "revise")
      state(list(tone = "warning", title = "Vorschlag als Korrektur übernommen", copy = "Symbol, Börse und Kurswährung ersetzen die gespeicherte Zuordnung erst nach „Zuordnung prüfen“, Bestätigen und „Zuordnung speichern“; danach „Jetzt einrichten“. Vorhandene Kurshistorie bleibt erhalten."))
    } else {
      state(list(tone = "neutral", title = "Vorschlag sichtbar übernommen", copy = "Die Felder bleiben editierbar; gespeichert wird erst nach der separaten Mappingvorschau."))
    }
  })
  action_feedback$observe('probe', input$asset_center_provider_probe, {
    safe({
      asset_center_require_market(TRUE)
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      scope <- data_provider_mapping_editor_resolve_probe_scope_v1(asset_center_provider_editor, runtime$context, input$asset_center_mapping)
      scope$catalog_fingerprint <- NULL
      asset_center_provider_probe_service$preview(scope, as.character(input$asset_center_probe_start), as.character(input$asset_center_probe_end), now_utc())
    }, function(preview) {
      asset_center_provider_probe_preview(preview); asset_center_provider_probe_result(NULL)
      shiny::updateCheckboxInput(session, "asset_center_provider_probe_confirm", value = FALSE)
      asset_center_provider_online(list(
        tone = "warning", title = "Ein Testabruf der Tageskurse wartet auf Bestätigung",
        copy = "Noch erfolgte kein Netzwerkzugriff. Symbol, Währung, Zeitraum und genau ein Versuch sind gebunden."
      ))
      state(asset_center_provider_online())
    })
  })
  action_feedback$observe('probe', input$asset_center_provider_probe_execute, {
    preview <- asset_center_provider_probe_preview()
    if (is.null(preview)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("data_provider_probe_preview_required"))); return()
    }
    safe({ asset_center_require_market(TRUE); asset_center_provider_probe_service$execute(preview, isTRUE(input$asset_center_provider_probe_confirm)) }, function(result) {
      asset_center_provider_probe_result(result); asset_center_provider_probe_preview(NULL)
      shiny::updateCheckboxInput(session, "asset_center_provider_probe_confirm", value = FALSE)
      shiny::updateTextInput(session, "asset_center_listing_timezone", value = result$timezone_name)
      provider_catalog <- asset_center_provider_catalog(); selected_mapping <- if (is.null(provider_catalog)) list() else Filter(function(row) identical(row$ref, input$asset_center_mapping), provider_catalog$mappings)
      suggested_market <- if (length(selected_mapping) == 1L && !is.null(selected_mapping[[1L]]$mic_code)) selected_mapping[[1L]]$mic_code else {
        value <- toupper(gsub("[^A-Z0-9]+", "_", result$exchange)); value <- gsub("^_+|_+$", "", value); substr(value, 1L, 16L)
      }
      if (nchar(suggested_market) >= 2L) shiny::updateTextInput(session, "asset_center_listing_market", value = suggested_market)
      core <- asset_center_catalog(); selected_asset <- if (is.null(core)) NULL else tryCatch(data_asset_center_selected_v1(core, input$asset_center_asset), error = function(error) NULL)
      shiny::updateSelectInput(session, "asset_center_listing_calendar", selected = if (!is.null(selected_asset) && identical(selected_asset$asset_type, "crypto")) "continuous_24_7" else "weekday_exchange")
      asset_center_provider_online(list(
        tone = if (isTRUE(result$currency_match) && !isTRUE(result$split_review_required)) "positive" else "warning",
        title = "Testnachweis des Kursanbieters gespeichert",
        copy = paste(result$observed_day_count, "beobachtete Tage · Währung", result$observed_currency, "· Übernahme und Verifizierung der Kurszuordnung bleiben getrennt.")
      ))
      state(asset_center_provider_online())
    })
  })
  # Einrichtung in einem Zug: Testabruf, Listing-Freigabe und Verifizierung sind
  # fachlich drei Schritte, aber eine Entscheidung. Einzeln sind sie fuer viele Assets nicht zu schaffen (#283). Genau ein Providerabruf,
  # eine Bestaetigung; bricht ein Schritt ab, bleibt der erreichte Stand stehen
  # und die Meldung benennt die Stelle.
  # Testabruf, Listing-Freigabe und Verifizierung in einem Zug. Der Knopf
  # „Einrichtung erneuern“ ruft dieselbe Kette auf, damit eine erneuerte
  # Einrichtung nicht anders zustande kommt als die erste (#283, 23.09.2026).
  asset_center_setup_run <- function() {
    step <- "Testabruf"
    outcome <- tryCatch({
      asset_center_require_market(TRUE)
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      scope <- data_provider_mapping_editor_resolve_probe_scope_v1(asset_center_provider_editor, runtime$context, input$asset_center_mapping)
      probe_scope <- scope; probe_scope$catalog_fingerprint <- NULL
      probe_preview <- asset_center_provider_probe_service$preview(
        probe_scope, as.character(input$asset_center_probe_start), as.character(input$asset_center_probe_end), now_utc())
      probe <- asset_center_provider_probe_service$execute(probe_preview, TRUE)
      probe_private <- asset_center_provider_probe_service$resolve_probe(probe$probe_handle)

      step <- "Freigabe der Notierung"
      core <- asset_center_catalog()
      selected_asset <- if (is.null(core)) NULL else tryCatch(data_asset_center_selected_v1(core, input$asset_center_asset), error = function(error) NULL)
      calendar <- if (!is.null(selected_asset) && identical(selected_asset$asset_type, "crypto")) "continuous_24_7" else "weekday_exchange"
      market <- gsub("^_+|_+$", "", gsub("[^A-Z0-9]+", "_", toupper(probe$exchange)))
      if (nchar(market) < 2L) market <- toupper(input$asset_center_listing_market)
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      scope <- data_provider_mapping_editor_resolve_probe_scope_v1(asset_center_provider_editor, runtime$context, input$asset_center_mapping)
      if (!identical(scope$mapping_fingerprint, probe_private$mapping_ref_fingerprint)) stop("desktop_provider_promotion_probe_invalid", call. = FALSE)
      promotion_preview <- asset_center_provider_promotion_service$preview(
        probe_private$request_ref, scope, substr(market, 1L, 16L), probe$timezone_name, calendar, now_utc())
      promotion <- asset_center_provider_promotion_service$execute(promotion_preview, TRUE, now_utc())

      step <- "Verifizierung"
      evidence <- asset_center_provider_promotion_service$resolve_promotion(promotion$promotion_handle)
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      scope <- data_provider_mapping_editor_resolve_probe_scope_v1(asset_center_provider_editor, runtime$context, input$asset_center_mapping)
      if (!identical(scope$mapping_id, evidence$mapping_id) || !identical(scope$mapping_fingerprint, evidence$mapping_fingerprint)) stop("data_provider_mapping_input_invalid", call. = FALSE)
      verify_preview <- data_provider_mapping_editor_prepare_verify_v1(
        asset_center_provider_editor, runtime$context, input$asset_center_mapping, evidence$probe_evidence_fingerprint, now_utc())
      data_provider_mapping_editor_execute_v1(asset_center_provider_editor, runtime$context, verify_preview, TRUE)
      list(status = "completed", observed = probe$observed_day_count, market = substr(market, 1L, 16L),
           calendar = calendar, listing_ref = evidence$listing_ref)
    }, error = function(error) list(status = "failed", code = spotcore::desktop_product_safe_error_code_v1(error)))
    outcome$step <- step
    outcome
  }
  # Eine Listing-Freigabe aus einer aelteren Produktversion passt nicht mehr zum
  # heutigen Stammdatenstand; der Kursabruf weist sie ab. Neu geschrieben wird
  # sie nur durch eine Freigabe, die frische Testevidenz braucht - und die
  # verlangt eine ungepruefte Zuordnung. Wer das von Hand macht, korrigiert
  # zuerst eine Zuordnung, an der nichts zu korrigieren ist. Der Knopf nimmt
  # diesen Umweg ab; an Anbieter, Symbol und Waehrung aendert er nichts
  # (#283).
  action_feedback$observe('setup', input$asset_center_setup_renew, {
    previous_listing <- NULL
    reset <- tryCatch({
      asset_center_require_market(TRUE)
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      row <- asset_center_provider_editor$state$mapping_map[[input$asset_center_mapping]]
      if (is.null(row)) stop("asset_center_market_selection_invalid", call. = FALSE)
      # Die bisherige Freigabe muss vor dem Zuruecksetzen festgehalten werden:
      # Danach gibt es sie nicht mehr als die des Assets.
      previous_listing <<- tryCatch({
        recovered <- asset_center_provider_promotion_service$recover(row$mapping_id)
        if (is.null(recovered)) NULL else
          asset_center_provider_promotion_service$resolve_promotion(recovered$promotion_handle)$listing_ref
      }, error = function(error) NULL)
      if (!identical(row$verification_status, "unverified")) {
        text <- function(value) if (is.null(value) || length(value) != 1L || is.na(value)) "" else as.character(value)
        form <- list(action = "revise", mapping_ref = input$asset_center_mapping,
          asset_ref = input$asset_center_asset, capability = row$capability,
          provider_id = row$provider_id, provider_symbol = row$provider_symbol,
          exchange_code = text(row$exchange_code), mic_code = toupper(text(row$mic_code)),
          provider_currency = toupper(row$provider_currency),
          expert_only = isTRUE(as.logical(row$expert_only)))
        preview <- data_provider_mapping_editor_prepare_v1(
          asset_center_provider_editor, runtime$context, form, now_utc())
        invisible(data_provider_mapping_editor_execute_v1(
          asset_center_provider_editor, runtime$context, preview, TRUE))
      }
      list(status = "ready")
    }, error = function(error) list(status = "failed",
      code = spotcore::desktop_product_safe_error_code_v1(error)))
    if (identical(reset$status, "failed")) {
      invisible(asset_center_refresh(input$asset_center_asset))
      state(list(tone = "error", title = "Erneuerung abgebrochen bei: Zuordnung zurücksetzen",
        copy = paste("Die gespeicherte Zuordnung ist unverändert; es wurde nichts abgerufen.", pl_error_text_v1(reset$code))))
      return()
    }
    outcome <- asset_center_setup_run(); market_setup_failed(identical(outcome$status, "failed"))
    # Die Kurshistorie haengt an der Freigabe, und die Erneuerung hat eine neue
    # angelegt. Statt dieselben Tage erneut bei der Quelle zu holen, werden sie
    # aus der Vorgaengerfreigabe uebernommen - lesend im eigenen Bestand, ohne
    # Anbieterzugriff. Uebernommen wird nur, was das Ziel noch nicht hat
    # (#283, 24.09.2026).
    carried <- if (!identical(outcome$status, "completed") || is.null(previous_listing) ||
                   identical(previous_listing, outcome$listing_ref)) NULL else
      tryCatch(asset_center_carry_service$carry(previous_listing, outcome$listing_ref,
        "2015-01-01", as.character(Sys.Date() - 1L), now_utc()),
        # Jede Strecke wird einzeln geschrieben. Scheitert eine spaetere, sind
        # fruehere schon dauerhaft da - "nichts uebernommen" waere dann falsch
        # und wuerde zu einem ueberfluessigen Neuabruf verleiten
        # (Prüfung 25.09.2026).
        error = function(error) list(failed = TRUE,
          code = spotcore::desktop_product_safe_error_code_v1(error)))
    asset_center_provider_probe_preview(NULL); asset_center_provider_promotion_preview(NULL); asset_center_mapping_verify_preview(NULL)
    invisible(asset_center_refresh(input$asset_center_asset))
    if (identical(outcome$status, "failed")) {
      state(list(tone = "error", title = paste("Erneuerung abgebrochen bei:", outcome$step),
        copy = paste0("Die Zuordnung steht jetzt auf „ungeprüft“ und ist deaktiviert; vorhandene Kurse bleiben erhalten. ",
          "Mit „Jetzt einrichten“ lässt sich der Lauf fortsetzen. ", pl_error_text_v1(outcome$code))))
    } else {
      state(list(tone = "positive", title = "Einrichtung erneuert",
        copy = paste0(outcome$observed, " beobachtete Tage · Markt ", outcome$market, " · Kalender ", outcome$calendar,
          " · Die Freigabe der Notierung trägt wieder den aktuellen Stammdatenstand, die Zuordnung ist verifiziert und aktiv. ",
          if (is.null(carried)) "Aus der bisherigen Freigabe war nichts zu übernehmen; die Kurshistorie muss abgerufen werden. "
          else if (isTRUE(carried$failed)) paste0("Die Übernahme aus der bisherigen Freigabe ist abgebrochen; ",
            "bereits geschriebene Strecken bleiben erhalten, der Rest muss abgerufen werden. ",
            pl_error_text_v1(carried$code), " ")
          else paste0(as.integer(carried$carried_day_count),
            " Kurstage wurden aus der bisherigen Freigabe übernommen — ohne Abruf bei der Quelle. "),
          "Fehlende Tage holt „Prüfen, was fehlt“ oder der Sammellauf.")))
    }
  })
  action_feedback$observe('setup', input$asset_center_setup_execute, {
    outcome <- asset_center_setup_run(); market_setup_failed(identical(outcome$status, "failed"))
    step <- if (is.null(outcome$step)) "Testabruf" else outcome$step
    asset_center_provider_probe_preview(NULL); asset_center_provider_promotion_preview(NULL); asset_center_mapping_verify_preview(NULL)
    invisible(asset_center_refresh(input$asset_center_asset))
    if (identical(outcome$status, "failed")) {
      state(list(tone = "error", title = paste("Einrichtung abgebrochen bei:", step),
        copy = paste("Der bis dahin erreichte Stand bleibt erhalten.", pl_error_text_v1(outcome$code))))
    } else {
      state(list(tone = "positive", title = "Einrichtung abgeschlossen",
        copy = paste0(outcome$observed, " beobachtete Tage · Markt ", outcome$market, " · Kalender ", outcome$calendar,
          " · Zuordnung verifiziert und aktiv. Kurshistorie und Bewertung bleiben eigene Schritte.")))
    }
  })
  action_feedback$observe('promotion', input$asset_center_promotion_prepare, {
    probe <- asset_center_provider_probe_result()
    if (is.null(probe) || is.null(probe$probe_handle)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("data_provider_promotion_preview_required"))); return()
    }
    safe({
      asset_center_require_market(TRUE)
      probe_private <- asset_center_provider_probe_service$resolve_probe(probe$probe_handle)
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      scope <- data_provider_mapping_editor_resolve_probe_scope_v1(asset_center_provider_editor, runtime$context, input$asset_center_mapping)
      if (!identical(scope$mapping_fingerprint, probe_private$mapping_ref_fingerprint)) stop("desktop_provider_promotion_probe_invalid", call. = FALSE)
      asset_center_provider_promotion_service$preview(
        probe_private$request_ref, scope, toupper(input$asset_center_listing_market),
        input$asset_center_listing_timezone, input$asset_center_listing_calendar, now_utc()
      )
    }, function(preview) {
      asset_center_provider_promotion_preview(preview); asset_center_provider_promotion_result(NULL)
      shiny::updateCheckboxInput(session, "asset_center_promotion_confirm", value = FALSE)
      state(list(tone = "neutral", title = "Übernahme der Historie geprüft", copy = "Kein Kursabruf; noch wurde keine Markthistorie geschrieben."))
    })
  })
  action_feedback$observe('promotion', input$asset_center_promotion_execute, {
    preview <- asset_center_provider_promotion_preview()
    if (is.null(preview)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("data_provider_promotion_preview_required"))); return()
    }
    safe({ asset_center_require_market(TRUE); asset_center_provider_promotion_service$execute(preview, isTRUE(input$asset_center_promotion_confirm), now_utc()) }, function(result) {
      asset_center_provider_promotion_result(result); asset_center_provider_promotion_preview(NULL)
      shiny::updateCheckboxInput(session, "asset_center_promotion_confirm", value = FALSE)
      asset_center_history_state(if (result$source_gap_day_count > 0L) "source_gap" else "partial")
      state(list(tone = "positive", title = "Testdaten persistent übernommen", copy = "Die Historie (Schema 2300) wird nur fortgeschrieben; die Kurszuordnung bleibt bis zur nächsten Bestätigung ungeprüft."))
    })
  })
  action_feedback$observe('verification', input$asset_center_mapping_verify_prepare, {
    promotion <- asset_center_provider_promotion_result()
    if (is.null(promotion) || is.null(promotion$promotion_handle)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("data_provider_promotion_preview_required"))); return()
    }
    safe({
      asset_center_require_market(TRUE)
      evidence <- asset_center_provider_promotion_service$resolve_promotion(promotion$promotion_handle)
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      scope <- data_provider_mapping_editor_resolve_probe_scope_v1(asset_center_provider_editor, runtime$context, input$asset_center_mapping)
      if (!identical(scope$mapping_id, evidence$mapping_id) || !identical(scope$mapping_fingerprint, evidence$mapping_fingerprint)) stop("data_provider_mapping_input_invalid", call. = FALSE)
      data_provider_mapping_editor_prepare_verify_v1(
        asset_center_provider_editor, runtime$context, input$asset_center_mapping,
        evidence$probe_evidence_fingerprint, now_utc()
      )
    }, function(preview) {
      asset_center_mapping_verify_preview(preview)
      shiny::updateCheckboxInput(session, "asset_center_mapping_verify_confirm", value = FALSE)
      state(list(tone = "neutral", title = "Verifizierung der Kurszuordnung geprüft", copy = "Der gespeicherte Testnachweis ist exakt an Kurszuordnung und Fassung gebunden."))
    })
  })
  action_feedback$observe('verification', input$asset_center_mapping_verify_execute, {
    preview <- asset_center_mapping_verify_preview()
    if (is.null(preview)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("data_provider_mapping_preview_required"))); return()
    }
    safe({ asset_center_require_market(TRUE); data_provider_mapping_editor_execute_v1(asset_center_provider_editor, runtime$context, preview, isTRUE(input$asset_center_mapping_verify_confirm)) }, function(result) {
      asset_center_mapping_verify_preview(NULL); shiny::updateCheckboxInput(session, "asset_center_mapping_verify_confirm", value = FALSE)
      invisible(asset_center_refresh(input$asset_center_asset))
      state(list(tone = "positive", title = "Kurszuordnung verifiziert", copy = "Die Kurszuordnung ist aktiv; weitere Historienabrufe holen nur Fehlendes und werden getrennt bestätigt."))
    })
  })
  shiny::observeEvent(input$asset_center_tax_initialize, {
    if (!isTRUE(input$asset_center_tax_initialize_confirm)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("tax_ui_confirmation_required"))); return()
    }
    safe(asset_center_tax_service$initialize(), function(value) {
      shiny::updateCheckboxInput(session, "asset_center_tax_initialize_confirm", value = FALSE)
      asset_center_tax_state("not_configured")
      invisible(asset_center_refresh_tax())
      state(list(tone = "positive", title = "Steuerbereich eingerichtet", copy = "Es wurde noch keine Klassifikation gesetzt."))
    })
  })
  shiny::observeEvent(input$asset_center_tax_refresh, safe(asset_center_refresh_tax(), function(value) {
    state(list(tone = "neutral", title = "Steuerdaten gelesen", copy = "Die Product-Asset-Auswahl ist ohne alten schema-400-Zwischenkatalog verfügbar."))
  }))
  shiny::observeEvent(list(input$asset_center_tax_portfolio, input$asset_center_tax_asset, input$asset_center_tax_year), {
    if (!isTRUE(asset_center_tax_service$initialized()) || is.null(input$asset_center_tax_portfolio) || !nzchar(input$asset_center_tax_portfolio) || is.null(input$asset_center_tax_asset) || !nzchar(input$asset_center_tax_asset) || is.null(input$asset_center_tax_year)) return(invisible(NULL))
    overview <- tryCatch(asset_center_tax_service$overview(input$asset_center_tax_portfolio, as.integer(input$asset_center_tax_year)), error = function(error) NULL)
    asset_center_tax_overview(overview)
    configured <- !is.null(overview) && any(vapply(overview$classifications, function(row) identical(row$asset_ref, input$asset_center_tax_asset) && identical(row$status, "active"), logical(1L)))
    asset_center_tax_state(if (configured) "complete" else "not_configured")
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$asset_center_tax_classification, {
    code <- input$asset_center_tax_classification
    if (is.null(code) || !nzchar(code)) return(invisible(NULL))
    shiny::updateTextInput(session, "asset_center_tax_partial", value = data_asset_center_tax_partial_for_v1(code))
    # Nur Fonds tragen einen Satz; fuer alle anderen Einordnungen ist die Fondsart
    # gegenstandslos und wird zurueckgesetzt, damit sie keinen Satz vortaeuscht.
    shiny::updateSelectInput(session, "asset_center_tax_fund_kind", selected = "")
  }, ignoreInit = TRUE)
  # Die Fondsart setzt den Prozentwert; geaendert werden kann er danach weiter von Hand,
  # denn gespeichert wird der ausdrueckliche Wert (#466).
  shiny::observeEvent(input$asset_center_tax_fund_kind, {
    rate <- input$asset_center_tax_fund_kind
    if (is.null(rate) || !nzchar(rate)) return(invisible(NULL))
    shiny::updateTextInput(session, "asset_center_tax_partial", value = rate)
  }, ignoreInit = TRUE)
  # Die Rueckmeldung der Abweichung je Asset steht am Formular (#427) - die Seitenleiste allein wird uebersehen.
  asset_center_tax_notice <- shiny::reactiveVal(NULL)
  output$asset_center_tax_notice <- shiny::renderUI({
    current <- asset_center_tax_notice()
    if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone)
  })
  asset_center_tax_notice_failure <- function(title) {
    current <- shiny::isolate(state())
    asset_center_tax_notice(list(tone = "error", title = title, copy = if (is.list(current) && is.character(current$copy)) current$copy else ""))
  }
  shiny::observeEvent(input$asset_center_tax_prepare, {
    checked <- FALSE
    safe(asset_center_tax_service$preview("set_asset_classification", asset_center_tax_payload()), function(preview) {
      checked <<- TRUE
      asset_center_tax_preview(preview); shiny::updateCheckboxInput(session, "asset_center_tax_confirm", value = FALSE)
      state(list(tone = "neutral", title = "Abweichung geprüft", copy = "Noch ist nichts gespeichert."))
      asset_center_tax_notice(list(tone = "warning", title = "Abweichung geprüft – noch nicht gespeichert",
        copy = "Bestätigen und „Abweichung speichern“ drücken. Neu gerechnet wird beim nächsten Portfolioabschluss."))
    })
    if (!checked) asset_center_tax_notice_failure("Abweichung nicht geprüft")
  })
  shiny::observeEvent(input$asset_center_tax_execute, {
    preview <- asset_center_tax_preview()
    if (is.null(preview)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("tax_ui_preview_missing")))
      asset_center_tax_notice(list(tone = "error", title = "Abweichung nicht gespeichert", copy = "Bitte zuerst „Abweichung prüfen“ drücken."))
      return()
    }
    written <- FALSE
    safe(asset_center_tax_service$confirm_apply(preview$preview_ref, isTRUE(input$asset_center_tax_confirm)), function(result) {
      written <<- TRUE
      asset_center_tax_preview(NULL); asset_center_tax_state("complete")
      shiny::updateCheckboxInput(session, "asset_center_tax_confirm", value = FALSE)
      state(list(tone = "positive", title = "Abweichung gespeichert", copy = "Neu gerechnet wird beim nächsten Portfolioabschluss."))
      asset_center_tax_notice(list(tone = "positive", title = "Abweichung gespeichert",
        copy = "Für dieses Asset gilt jetzt die eigene Klassifikation statt der Vorgabe seines Typs. Neu gerechnet wird beim nächsten Portfolioabschluss."))
    })
    if (!written) asset_center_tax_notice_failure("Abweichung nicht gespeichert")
  })
  # Loest offene Wechselkurs-Versuche auf: Gestagtes wird ohne neuen Abruf
  # veroeffentlicht, alles andere quittiert. Gibt die Zahl der aufgeloesten
  # Versuche zurueck.
  asset_center_resolve_open_fx <- function() asset_center_chain$resolve_open_fx()
  asset_center_recover_history_promotion <- function() {
    promotion <- asset_center_provider_promotion_result()
    if (!is.null(promotion) && !is.null(promotion$promotion_handle)) return(promotion)
    recovered <- tryCatch({
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      scope <- data_provider_mapping_editor_resolve_history_scope_v1(asset_center_provider_editor, runtime$context, input$asset_center_mapping)
      asset_center_provider_promotion_service$recover(scope$mapping_id)
    }, error = function(error) NULL)
    if (!is.null(recovered)) asset_center_provider_promotion_result(recovered)
    recovered
  }
  # Aktualisierung bis gestern: planen, holen, veroeffentlichen, bewerten. Die
  # Planung schreibt nichts und nennt die Zahl der Abrufe; erst die Bestaetigung
  # loest sie aus (#283, Festlegung 20.09.2026).
  asset_center_refresh_plan <- shiny::reactiveVal(NULL)
  asset_center_refresh_pending <- shiny::reactiveVal(NULL)
  asset_center_refresh_target <- function() {
    promotion <- asset_center_recover_history_promotion()
    if (is.null(promotion) || is.null(promotion$promotion_handle)) stop("data_market_history_review_service_invalid", call. = FALSE)
    private <- asset_center_provider_promotion_service$resolve_promotion(promotion$promotion_handle)
    invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
    mapping <- data_provider_mapping_editor_resolve_history_scope_v1(asset_center_provider_editor, runtime$context, input$asset_center_mapping)
    list(private = private, mapping = mapping, binding = list(
      listing_ref = private$listing_ref, listing_fingerprint = private$listing_fingerprint,
      mapping_id = private$mapping_id, mapping_revision = as.integer(private$mapping_revision),
      mapping_fingerprint = private$mapping_fingerprint))
  }
  # Der Bewertungszeitraum setzt die Felder der Einzelschritte mit, damit niemand
  # vier Datumspaare pflegen muss. Der Testabruf braucht nur ein kurzes Fenster am
  # Ende des Zeitraums (#283, 21.09.2026).
  shiny::observeEvent(list(input$asset_center_period_start, input$asset_center_period_end), {
    from <- input$asset_center_period_start; to <- input$asset_center_period_end
    if (length(from) != 1L || length(to) != 1L || is.na(from) || is.na(to) || as.Date(to) < as.Date(from)) return()
    probe_start <- max(as.Date(from), as.Date(to) - 13L)
    for (pair in list(c("asset_center_coverage_start", "asset_center_coverage_end"),
                      c("asset_center_fx_history_start", "asset_center_fx_history_end"),
                      c("asset_center_history_start", "asset_center_history_end"))) {
      shiny::updateDateInput(session, pair[[1L]], value = as.Date(from))
      shiny::updateDateInput(session, pair[[2L]], value = as.Date(to))
    }
    shiny::updateDateInput(session, "asset_center_probe_start", value = probe_start)
    shiny::updateDateInput(session, "asset_center_probe_end", value = as.Date(to))
  }, ignoreInit = FALSE)
  # Beim Assetwechsel beginnt der Zeitraum bei dessen erster Buchung. Die
  # Buchungsansicht fuehrt Activity-Editor-Refs, die Assetauswahl Katalog-Refs;
  # ohne Uebersetzung traf der Vergleich nie zu und der Zeitraum blieb still auf
  # dem Vorgabewert stehen (#283, 21.09.2026).
  asset_center_first_booking <- function(asset_ref) {
    if (is.null(asset_ref) || !length(asset_ref) || !nzchar(asset_ref)) return(NULL)
    asset_ref <- activity_ref_for_center("asset", asset_ref)
    if (!nzchar(asset_ref)) return(NULL)
    projection <- tryCatch({
      view <- activity_read_view(); catalog <- activity_catalog()
      if (is.null(view) || is.null(catalog)) NULL else
        asset_selection_context_project_activity_v3(catalog, view, scope_mode = "all")
    }, error = function(error) NULL)
    if (is.null(projection)) return(NULL)
    dates <- character(0)
    for (portfolio in projection$portfolios) for (row in portfolio$events_newest_first) {
      if (identical(row$asset_ref, asset_ref) && is.character(row$local_date) && length(row$local_date) == 1L)
        dates <- c(dates, row$local_date)
    }
    if (!length(dates)) NULL else min(dates)
  }
  # Vor der Erstnotiz gibt es keinen Kurs; ein frueherer Beginn erzeugt nur Tage,
  # die niemand bewerten kann. Der erste gespeicherte Tag ist nicht der erste
  # Kurstag, deshalb fragen wir ausdruecklich nach der Erstnotiz.
  # Das gehoert in die angeforderte Planung, nicht an die Assetauswahl: Das
  # Aufloesen des Ziels frischt den Zuordnungseditor auf, und eine solche
  # Auffrischung verwirft einen offenen Bewertungsentwurf (#283, 21.09.2026).
  asset_center_first_observed <- function(target, from, until, asset_ref = input$asset_center_asset, mapping_ref = input$asset_center_mapping)
    asset_center_chain$first_observed(target, from, until, asset_ref, mapping_ref)
  # Bewusst kein reaktives Vorbelegen an der Assetauswahl: Die Buchungsansicht
  # trifft oft erst Sekunden spaeter ein, der Zeitraum steuert die
  # Abdeckungsfelder, und deren spaete Aenderung verwirft einen inzwischen
  # erstellten Bewertungsentwurf kommentarlos. Der Zeitraum wird deshalb in der
  # angeforderten Planung gesetzt, wo der Eigentuemer geklickt hat und noch kein
  # Entwurf offen ist (#283, 21.09.2026).
  output$asset_center_refresh_action <- shiny::renderUI({
    planned <- asset_center_refresh_plan()
    if (is.null(planned)) return(shiny::span(class = "pl-field-hint", "Zuerst prüfen, was fehlt."))
    fx_ranges <- if (is.null(planned$fx_plan)) 0L else as.integer(planned$fx_plan$range_count)
    total <- as.integer(planned$plan$range_count) + fx_ranges
    shiny::actionButton("asset_center_refresh_execute",
      if (total > 0L) sprintf("%d Abrufe starten, veröffentlichen und Vorschau erstellen", total) else "Ohne Abruf Vorschau erstellen",
      class = "btn-primary")
  })
  # Welche Bewertungsmethode gilt fuer das gewaehlte Asset? Nur die
  # Provider-Marktbewertung braucht Zuordnung, Abruf und Wechselkurse; Einheitswert
  # und bestaetigte Trade-Kurse rechnen ohne jeden Provider (#283 Punkt 2).
  # Innerhalb der manuellen Methode gibt es zwei providerfreie Quellen. Welche
  # gilt, sagt der Eigentuemer; stillschweigend eine davon zu nehmen waere geraten.
  asset_center_manual_source <- function() {
    value <- input$asset_center_manual_source
    if (is.character(value) && length(value) == 1L && nzchar(value)) value else "own_entries"
  }
  asset_center_selected_method <- function() {
    selected <- tryCatch(asset_center_selected(), error = function(error) NULL)
    if (is.null(selected) || !is.character(selected$valuation_method)) "external_market" else selected$valuation_method
  }
  # Die read-only-Planung - Zeitraum bestimmen, fehlende Kurs- und
  # Wechselkurstage zaehlen - gilt fuer das einzelne Asset wie fuer den
  # Sammellauf (#283, 23.09.2026).
  # Das Ende, das die Planung meldet, wenn es frueher liegt als das gewuenschte (#475).
  asset_center_completed_until <- function(until, reported) asset_center_chain$completed_until(until, reported)
  asset_center_not_completed_plan <- function(target, from, until, listed_since) asset_center_chain$not_completed_plan(target, from, until, listed_since)
  asset_center_chain_plan <- function(asset_ref, period_start, period_end, period_mode = "from_first_trade",
                                      valuation_method = asset_center_selected_method(), manual_source = asset_center_manual_source(),
                                      target = NULL, mapping_ref = input$asset_center_mapping) {
    # Ohne uebergebenes Ziel gilt die Auswahl der Oberflaeche - nur die Provider-Marktbewertung braucht eines.
    if (identical(valuation_method, "external_market") && is.null(target)) target <- asset_center_refresh_target()
    asset_center_chain$chain_plan(asset_ref, period_start, period_end, period_mode, valuation_method, manual_source, target, mapping_ref)
  }
  action_feedback$observe('refresh', input$asset_center_refresh_plan, {
    safe({
      asset_center_chain_plan(input$asset_center_asset, input$asset_center_period_start,
        input$asset_center_period_end,
        if (is.character(input$asset_center_period_mode) && length(input$asset_center_period_mode) == 1L)
          input$asset_center_period_mode else "from_first_trade")
    }, function(value) {
      if (isTRUE(value$provider_free)) {
        asset_center_refresh_plan(value)
        state(list(tone = "positive", title = "Ohne Kursanbieter bewertbar",
          copy = paste0(if (identical(value$method, "unit_value")) "Einheitswert: jede Einheit zählt 1 in der fachlichen Währung."
            else if (identical(asset_center_manual_source(), "trade_prices")) "Bestätigte Trade-Stückpreise werden fortgeschrieben; sie sind keine Marktkurse und werden als Ersatzwerte gekennzeichnet."
            else "Eigene Kursangaben werden fortgeschrieben; sie sind keine Marktkurse und werden als Ersatzwerte gekennzeichnet.",
            " Zeitraum ", format(as.Date(value$from), "%d.%m.%Y"), " bis ", format(as.Date(value$until), "%d.%m.%Y"),
            ". Es wird nichts abgerufen.")))
        return()
      }
      if (isTRUE(value$period_invalid)) {
        asset_center_refresh_plan(NULL)
        state(list(tone = "warning", title = "Beginn liegt nach der ersten Transaktion",
          copy = paste0("Der Modus „vor erster Transaktion“ verlangt einen Beginn bis spätestens ",
            format(as.Date(value$booked), "%d.%m.%Y"), "; eingetragen ist ", format(as.Date(value$from), "%d.%m.%Y"),
            ". Bitte den Beginn vorziehen oder „freie Datumswahl“ verwenden. Es wurde nichts abgerufen.")))
        return()
      }
      if (isTRUE(value$not_completed_yet)) {
        asset_center_refresh_plan(NULL)
        state(list(tone = "warning", title = "Noch kein abgeschlossener Handelstag",
          copy = paste0("Der Zeitraum beginnt am ", format(as.Date(value$from), "%d.%m.%Y"),
            "; dieser Tag ist in der Zeitzone der Notierung noch nicht vorbei. Ein laufender Kurs würde als Tageswert gespeichert. ",
            "Später erneut prüfen. Es wurde nichts abgerufen.")))
        return()
      }
      if (isTRUE(value$not_listed_yet)) {
        asset_center_refresh_plan(NULL)
        state(list(tone = "warning", title = paste0("Noch nicht notiert am ",
          format(as.Date(value$until), "%d.%m.%Y")),
          copy = paste0("Die Quelle führt diesen Titel erst ab ", format(as.Date(value$listed_since), "%d.%m.%Y"),
            ". Der gewählte Zeitraum endet davor, es gibt also keinen Kurstag. Bitte das Ende nach hinten setzen. Es wurde nichts abgerufen.")))
        return()
      }
      asset_center_refresh_plan(value)
      # Der Eigentuemer soll sehen, ab wann ueberhaupt bewertet werden kann.
      if (!identical(value$from, as.character(input$asset_center_period_start)))
        shiny::updateDateInput(session, "asset_center_period_start", value = as.Date(value$from))
      if (isTRUE(value$fx_missing)) {
        asset_center_refresh_plan(NULL)
        state(list(tone = "warning", title = paste0("Wechselkurs-Paar ", value$currency, "/EUR fehlt"),
          copy = paste0("Der Kurs steht in ", value$currency, ", deshalb wird das Paar gebraucht. Bitte im FX-Abschnitt ein Paar suchen, den Treffer prüfen und übernehmen; danach diese Planung erneut ausführen. Es wurde nichts abgerufen.")))
        return()
      }
      fx_days <- if (is.null(value$fx_plan)) 0L else as.integer(value$fx_plan$target_day_count)
      fx_ranges <- if (is.null(value$fx_plan)) 0L else as.integer(value$fx_plan$range_count)
      open <- as.integer(value$plan$target_day_count) + fx_days
      state(list(tone = if (open > 0L) "warning" else "positive",
        title = if (open > 0L)
          paste0(value$plan$target_day_count, " fehlende Kurstage in ", value$plan$range_count, " Abrufen · ",
                 fx_days, " fehlende Kurstage für ", value$currency, "/EUR in ", fx_ranges, " Abrufen")
        else "Kurse und Wechselkurse sind im Zeitraum vollständig",
        copy = paste0("Zeitraum ", format(as.Date(value$from), "%d.%m.%Y"), " bis ", format(as.Date(value$until), "%d.%m.%Y"),
          ". Die Planung war read-only; erst die Bestätigung löst Abrufe aus. Anschließend wird bewertet und abgeschlossen.",
          if (open == 0L) " Vorhandene Kurse werden dabei nicht erneut abgerufen." else "",
          if (!is.na(value$fx_as_of)) paste0(" Umrechnungsbasis ", value$currency, "/EUR: jüngster Kurs ", format(as.Date(value$fx_as_of), "%d.%m.%Y"),
            " (", as.integer(Sys.Date() - as.Date(value$fx_as_of)), " Tage alt); spätere Tage werden fortgeschrieben.") else "",
          if (as.integer(value$open_fx) > 0L) paste0(" Dazu ", value$open_fx, " offene Wechselkurs-Versuche aus früheren Läufen, die zuerst aufgelöst werden.") else "",
          # Ein spaeterer Beginn als gewuenscht braucht eine Begruendung, sonst
          # sieht er aus wie ein Fehler (Festlegung 25.09.2026, #283).
          if (is.character(value$listed_since) && length(value$listed_since) == 1L && !is.na(value$listed_since))
            paste0(" Erstnotiz laut Quelle: ", format(as.Date(value$listed_since), "%d.%m.%Y"),
              "; davor gibt es keinen Kurs und deshalb auch keinen offenen Tag.") else "")))
    })
  })
  # Die Kette - offene Wechselkurs-Versuche aufloesen, Wechselkurse holen,
  # Kurse holen, Schliesstage binden, bewerten - gilt fuer das einzelne Asset
  # wie fuer den Sammellauf. Beide rufen denselben Code auf; ein Sammellauf,
  # der stillschweigend etwas anderes taete als der Einzelschritt, waere nicht
  # nachpruefbar (#283, 23.09.2026).
  # require_selection: Nur der Einzelablauf prueft die Auswahl in der Oberflaeche.
  # Der Sammellauf hat sein Ziel bereits selbst aufgeloest; haengte er zusaetzlich
  # an der Auswahl, scheiterte jedes Asset, sobald diese nicht mehr zu ihrer
  # Zuordnung passt - etwa direkt nach einer Neuzuordnung. Dann
  # brachen alle Assets ab, obwohl mit ihnen nichts war
  # (26.09.2026, #283).
  asset_center_chain_run <- function(asset_ref, planned, target = NULL, manual_source = asset_center_manual_source(),
                                     require_selection = TRUE) {
    # Auswahl und Ziel der Oberflaeche: wie bisher als Teil des Kursabrufs; ein Fehler endet als Ergebnis, nicht als Abbruch.
    if (!isTRUE(planned$provider_free)) {
      refused <- tryCatch({
        if (isTRUE(require_selection)) asset_center_require_market(TRUE)
        if (is.null(target)) target <- asset_center_refresh_target()
        NULL
      }, error = function(error) list(status = "failed", code = asset_center_safe_code(error), step = "Kursabruf",
                                      fetched = 0L, fetched_fx = 0L, resolved_fx = 0L))
      if (!is.null(refused)) return(refused)
    }
    asset_center_chain$chain_run(asset_ref, planned, target, manual_source, FALSE)
  }
  # Sammellauf: dieselbe Kette, nur ohne Klick je Asset. Der Einzelablauf kostet pro Asset
  # sechs Klicks, und die Quelle bremst zwischendurch. Der Lauf arbeitet
  # deshalb ein Asset je Sekunde ab, haelt bei einer Abweisung der Quelle an und
  # setzt dort fort, wo er stand - veroeffentlichte Kurse bleiben erhalten, die
  # naechste Planung holt nur noch das Fehlende (#283, 23.09.2026).
  # Drei Abweisungen der Kursprüfung kommen regelmäßig
  # vor. Der nackte Code sagte jedes Mal nur, dass etwas nicht ging -
  # nicht, was zu tun ist (#283, 23.09.2026).
  # Ein `stop("asset_center_...")` traegt keinen Code, nur eine Meldung - der
  # sichere Code faellt dann auf den Sammelcode zurueck und verschweigt die
  # Ursache. Ist die Meldung selbst ein bekannter Code, gilt sie.
  asset_center_safe_code <- function(error) asset_center_chain$safe_code(error)
  asset_center_fetch_reason <- function(code) asset_center_chain$fetch_reason(code)
  asset_center_period_mode <- function() {
    value <- input$asset_center_period_mode
    if (is.character(value) && length(value) == 1L && nzchar(value)) value else "from_first_trade"
  }
  # Nur Assets, deren Zuordnung dieselbe Notierung beschreibt: gleicher
  # Anbieter, gleiches Symbol, gleiche Kurswaehrung. Alles andere waere ein
  # anderes Papier, und der Kursspeicher sieht das nicht - er kennt nur
  # Waehrung, Markt, Zeitzone und Kalender der Freigabe (#283, 24.09.2026).
  asset_center_carry_state <- shiny::reactiveVal(NULL)
  asset_center_carry_preview_value <- shiny::reactiveVal(NULL)
  asset_center_carry_resolve <- function(asset_ref) {
    inventory <- tryCatch(asset_center_valuation_inventory(), error = function(error) NULL)
    if (is.null(inventory)) return(NULL)
    rows <- Filter(function(row) identical(row$asset_ref, asset_ref) &&
      identical(row$status, "history_ready_to_plan"), inventory$rows)
    if (length(rows) != 1L) return(NULL)
    resolved <- tryCatch(asset_center_valuation_resolve(rows)[[1L]], error = function(error) NULL)
    if (is.null(resolved) || is.null(resolved$mapping) || is.null(resolved$listing_ref)) return(NULL)
    list(listing_ref = resolved$listing_ref, mapping = resolved$mapping, name = rows[[1L]]$asset_name)
  }
  asset_center_carry_candidates <- function() {
    inventory <- tryCatch(asset_center_valuation_inventory(), error = function(error) NULL)
    if (is.null(inventory)) return(character())
    providers <- tryCatch(asset_center_provider_catalog(), error = function(error) NULL)
    data_asset_center_carry_candidates_v1(inventory$rows, if (is.null(providers)) list() else providers$mappings,
      input$asset_center_asset, asset_center_carry_resolve)
  }
  # Ein Wechsel der Quelle verwirft die Vorschau: Sie gilt fuer die Quelle, an
  # der sie gerechnet wurde (Prüfung 25.09.2026).
  shiny::observeEvent(input$asset_center_carry_source, {
    asset_center_carry_preview_value(NULL)
    asset_center_carry_state(NULL)
    shiny::updateCheckboxInput(session, "asset_center_carry_confirm", value = FALSE)
  }, ignoreInit = TRUE)
  shiny::observeEvent(list(input$asset_center_asset, input$asset_center_step), {
    if (!identical(input$asset_center_step, "Marktdaten")) return()
    choices <- tryCatch(asset_center_carry_candidates(), error = function(error) character())
    asset_center_carry_state(NULL); asset_center_carry_preview_value(NULL)
    shiny::updateSelectInput(session, "asset_center_carry_source",
      choices = c("Bitte wählen" = "", choices), selected = "")
    shiny::updateCheckboxInput(session, "asset_center_carry_confirm", value = FALSE)
  }, ignoreInit = TRUE)
  asset_center_carry_run <- function(dry_run, reverse = FALSE, source_ref = input$asset_center_carry_source) {
    if (!is.character(source_ref) || length(source_ref) != 1L || !nzchar(source_ref))
      stop("asset_center_market_selection_invalid", call. = FALSE)
    target <- asset_center_carry_resolve(input$asset_center_asset)
    source <- asset_center_carry_resolve(source_ref)
    if (is.null(target) || is.null(source)) stop("asset_center_market_selection_invalid", call. = FALSE)
    if (!identical(source$mapping$provider_id, target$mapping$provider_id) ||
        !identical(source$mapping$provider_symbol, target$mapping$provider_symbol) ||
        !identical(source$mapping$provider_currency, target$mapping$provider_currency))
      stop("asset_center_market_selection_invalid", call. = FALSE)
    handler <- if (isTRUE(dry_run)) asset_center_carry_service$preview else asset_center_carry_service$carry
    from_ref <- if (isTRUE(reverse)) target$listing_ref else source$listing_ref
    to_ref <- if (isTRUE(reverse)) source$listing_ref else target$listing_ref
    list(result = handler(from_ref, to_ref, "2015-01-01",
      as.character(Sys.Date() - 1L), now_utc()), source_name = source$name,
      source_ref = source_ref)
  }
  shiny::observeEvent(input$asset_center_carry_preview, {
    outcome <- tryCatch(asset_center_carry_run(TRUE), error = function(error)
      list(failed = TRUE, code = spotcore::desktop_product_safe_error_code_v1(error)))
    asset_center_carry_preview_value(NULL)
    shiny::updateCheckboxInput(session, "asset_center_carry_confirm", value = FALSE)
    if (isTRUE(outcome$failed)) {
      asset_center_carry_state(list(tone = "error", title = "Vorschau nicht möglich",
        copy = paste("Es wurde nichts geschrieben.", pl_error_text_v1(outcome$code))))
      return()
    }
    days <- as.integer(outcome$result$carried_day_count)
    if (days == 0L) {
      # Wer die Richtung verwechselt, soll das erfahren, statt zu raten. Die
      # Gegenprobe rechnet dieselbe Vorschau mit vertauschten Freigaben und
      # schreibt ebenso wenig (Festlegung 24.09.2026, #283).
      reverse <- tryCatch(asset_center_carry_run(TRUE, reverse = TRUE), error = function(error) NULL)
      other <- if (is.null(reverse)) 0L else as.integer(reverse$result$carried_day_count)
      asset_center_carry_state(list(tone = "neutral", title = "In dieser Richtung ist nichts zu übernehmen",
        copy = paste0("Dieses Asset trägt bereits jeden Tag, den „", outcome$source_name, "“ hat. ",
          if (other > 0L) paste0("Umgekehrt wären es ", other, " Tage: Dafür „", outcome$source_name,
            "“ oben als Asset wählen und dieses hier als Quelle. ") else "Auch umgekehrt gibt es nichts zu holen. ",
          "Es wurde nichts geschrieben und nichts abgerufen.")))
      return()
    }
    # Geschrieben wird genau die geprüfte Quelle. Vorher las der Schreibschritt
    # das Auswahlfeld neu: Ein Wechsel nach der Vorschau hätte mit noch
    # gesetztem Häkchen eine ungeprüfte Reihe übernommen und damit die Zusage
    # „Vorschau vor dem Schreiben“ ausgehebelt.
    asset_center_carry_preview_value(list(result = outcome$result, source_ref = outcome$source_ref,
      source_name = outcome$source_name))
    asset_center_carry_state(list(tone = "neutral", title = "Vorschau · noch nichts übernommen",
      copy = paste0(days, " Kurstage aus „", outcome$source_name,
        "“ in ", as.integer(outcome$result$range_count), " Strecken. Es wurde nichts geschrieben und nichts abgerufen. ",
        "Zum Übernehmen das Häkchen setzen und „Übernehmen“ drücken.")))
  })
  shiny::observeEvent(input$asset_center_carry_execute, {
    if (is.null(asset_center_carry_preview_value())) {
      asset_center_carry_state(list(tone = "warning", title = "Zuerst prüfen",
        copy = "Bitte zuerst prüfen, was übernommen würde; ohne Vorschau wird nichts geschrieben."))
      return()
    }
    if (!isTRUE(input$asset_center_carry_confirm)) {
      asset_center_carry_state(list(tone = "warning", title = "Bestätigung fehlt",
        copy = "Die Übernahme hängt eine vorhandene Kursreihe an dieses Asset. Dafür das Häkchen setzen."))
      return()
    }
    checked <- asset_center_carry_preview_value()
    if (!identical(checked$source_ref, input$asset_center_carry_source)) {
      asset_center_carry_preview_value(NULL)
      shiny::updateCheckboxInput(session, "asset_center_carry_confirm", value = FALSE)
      asset_center_carry_state(list(tone = "warning", title = "Quelle wurde nach der Vorschau gewechselt",
        copy = paste0("Geprüft wurde „", checked$source_name, "“, ausgewählt ist jetzt etwas anderes. ",
          "Es wurde nichts geschrieben. Bitte erneut prüfen, was übernommen würde.")))
      return()
    }
    outcome <- tryCatch(asset_center_carry_run(FALSE, source_ref = checked$source_ref),
      error = function(error) list(failed = TRUE, code = spotcore::desktop_product_safe_error_code_v1(error)))
    asset_center_carry_preview_value(NULL)
    shiny::updateCheckboxInput(session, "asset_center_carry_confirm", value = FALSE)
    if (isTRUE(outcome$failed)) {
      asset_center_carry_state(list(tone = "error", title = "Übernahme abgebrochen",
        copy = paste("Es wurde nichts geschrieben.", pl_error_text_v1(outcome$code))))
      return()
    }
    asset_center_carry_state(list(tone = "positive", title = "Kursreihe übernommen",
      copy = paste0(as.integer(outcome$result$carried_day_count), " Kurstage aus „", outcome$source_name,
        "“ übernommen — ohne Abruf bei der Quelle. Sie bleiben als übernommen erkennbar. ",
        "Die Bewertung dieses Assets muss noch laufen: „Prüfen, was fehlt“ oder der Sammellauf.")))
  })
  output$asset_center_carry_state <- shiny::renderUI({
    value <- asset_center_carry_state()
    if (is.null(value)) return(NULL)
    portelyra_status_panel(value$title, value$copy, tone = value$tone)
  })
  asset_center_sweep <- shiny::reactiveValues(
    queue = list(), index = 0L, results = list(), running = FALSE,
    resume_at = NULL, attempts = 0L, prepared = FALSE, period = NULL)
  # Der Zeitraum gilt ab der Vorbereitung fuer den ganzen Lauf. Vorher las jeder Schritt die Felder des Reiters neu; ein
  # Lauf aus „Alles aktualisieren“ (#463) braucht seinen eigenen, festen Zeitraum - ab erster Buchung bis gestern.
  asset_center_sweep_period_inputs <- function() list(mode = asset_center_period_mode(),
    start = as.character(input$asset_center_period_start), end = as.character(input$asset_center_period_end))
  # Die Meldungen des Sammellaufs gehoeren an den Sammellauf. Seine Observer sind
  # gewoehnliche observeEvent und damit keinem Rueckmeldebereich zugeordnet; ihre
  # Meldungen landeten im allgemeinen Zustand, den beim Sammellauf niemand
  # ansieht. Eine abgelehnte Startanforderung sah deshalb aus, als passiere
  # nichts (Festlegung 23.09.2026, #283).
  asset_center_sweep_notice <- shiny::reactiveVal(NULL)
  # Der Sammellauf haelt dieselbe Sperre wie der Hintergrundlauf von „Alles aktualisieren“ (rc.315, #510): Beide schreiben Kurse
  # und Bewertungen; liefen sie zugleich, bewertete einer den Stand des anderen mit.
  asset_center_sweep_lock <- NULL
  asset_center_sweep_release <- function() {
    if (!is.null(asset_center_sweep_lock) && !is.null(refresh_all_store)) tryCatch(refresh_all_store$release(asset_center_sweep_lock), error = function(error) NULL)
    asset_center_sweep_lock <<- NULL
  }
  # Das Ziel einer Zeile kommt aus derselben Aufloesung wie im Bewertungslauf:
  # Zuordnung und Listing-Promotion muessen zueinander passen, sonst bewertet der
  # Lauf gegen ein Listing aus einer frueheren Mapping-Revision.
  asset_center_chain_target <- function(row) asset_center_chain$chain_target(row)
  # Nur Provider-Marktbewertung mit geprueftem Mapping. Eigene Kursangaben und
  # bestaetigte Trade-Stueckpreise bleiben aussen vor: Welche der beiden Quellen
  # gilt, sagt der Eigentuemer je Asset, und das darf ein Sammellauf nicht raten.
  # Fehlt einem Asset kein Kurstag, ist seine Bewertung schon geschrieben - sie
  # erneut zu rechnen kostet Zeit und aendert nichts. Der Lauf zaehlt deshalb
  # vorher, wem etwas fehlt. Das ist dieselbe Planung wie im Lauf, nur lesend:
  # kein Abruf, kein Netz (Festlegung 25.09.2026, #283).
  asset_center_sweep_missing <- function(row, until, notations = NULL, period = asset_center_sweep_period_inputs())
    asset_center_chain$sweep_missing(row, until, notations, period)
  asset_center_sweep_queue <- function(only_missing, period = asset_center_sweep_period_inputs()) asset_center_chain$sweep_queue(only_missing, period)
  asset_center_sweep_reset <- function() asset_center_chain$sweep_reset(asset_center_sweep)
  asset_center_sweep_step <- function() asset_center_chain$sweep_step(asset_center_sweep, asset_center_sweep_period_inputs)
  shiny::observeEvent(input$asset_center_sweep_prepare, {
    # Datenbestand an fremdem Ort ohne Bindung (#556): Bewertung und Kurszuordnung lehnen ab - vorher mit Grund anhalten.
    unbound <- data_relocation_blocked_copy_v1(data_relocation_status_v1(project_root, runtime_data_space_path(runtime$context)))
    if (!is.null(unbound)) {
      asset_center_sweep_notice(list(tone = "error", title = "Sammellauf nicht vorbereitet", copy = unbound))
      return()
    }
    period <- asset_center_sweep_period_inputs()
    prepared <- tryCatch(asset_center_sweep_queue(isTRUE(input$asset_center_sweep_only_missing), period),
      error = function(error) NULL)
    queue <- if (is.null(prepared)) NULL else prepared$ready
    if (is.null(queue)) {
      asset_center_sweep_notice(list(tone = "error", title = "Sammellauf nicht vorbereitet",
        copy = "Der Bestand liess sich nicht lesen. Bitte das Asset-Center oben neu lesen."))
      return()
    }
    asset_center_sweep_notice(NULL)
    asset_center_sweep_reset()
    asset_center_sweep$queue <- queue
    asset_center_sweep$period <- period
    asset_center_sweep$prepared <- TRUE
    state(list(tone = if (length(queue)) "warning" else "positive",
      title = if (!length(queue) && as.integer(prepared$complete) > 0L)
          "Nichts zu tun — jedes Asset ist auf dem Stand"
        else paste(length(queue), "Assets im Sammellauf"),
      copy = paste0("Gezählt wurden alle aktiven Assets mit Marktbewertung über einen Kursanbieter und geprüfter Kurszuordnung. ",
        "Die Vorbereitung war nur lesend: kein Abruf, kein Schreiben. Der Lauf selbst ruft ab, veröffentlicht ",
        "und schreibt je Asset die Bewertung - ohne Halt vor jedem Entwurf. ",
        switch(asset_center_period_mode(),
          from_first_trade = "Beginn je Asset bei dessen erster Buchung",
          before_first_trade = paste0("Beginn einheitlich ", format(as.Date(input$asset_center_period_start), "%d.%m.%Y"),
            "; Assets mit einer früheren ersten Buchung werden übersprungen"),
          paste0("Beginn einheitlich ", format(as.Date(input$asset_center_period_start), "%d.%m.%Y"), " für jedes Asset")),
        ", Ende ", format(min(as.Date(input$asset_center_period_end), Sys.Date() - 1L), "%d.%m.%Y"), ".",
        if (as.integer(prepared$complete) > 0L) paste0(" ", as.integer(prepared$complete),
          " Assets übersprungen, weil ihnen kein Kurstag fehlt — ihre Bewertung ist geschrieben.",
          " Zum Neuschreiben das Häkchen „nur Assets mit fehlenden Kurstagen“ entfernen und erneut vorbereiten.") else "",
        if (length(prepared$excluded)) paste0(" Nicht im Lauf: ",
          paste(vapply(names(prepared$excluded), function(key) paste0(prepared$excluded[[key]], " ",
            switch(key, mapping_missing = "ohne Zuordnung", mapping_test_required = "mit offenem Testabruf",
                   mapping_disabled = "mit deaktivierter Zuordnung", manual = "mit eigener Kursquelle",
                   unit_value = "mit Einheitswert", timeline_series_unmapped = "Kursreihen der Zeitleiste ohne heutige Zuordnung",
                   key)), character(1L)), collapse = ", "), ".") else "",
        data_market_timeline_blocked_copy_v1(prepared$timeline_blocked))))
  })
  shiny::observeEvent(input$asset_center_sweep_start, {
    if (!isTRUE(asset_center_sweep$prepared) || !length(asset_center_sweep$queue)) {
      asset_center_sweep_notice(list(tone = "warning", title = "Zuerst vorbereiten",
        copy = "Bitte zuerst den Sammellauf vorbereiten; ohne Liste wird nichts abgerufen."))
      return()
    }
    if (!isTRUE(input$asset_center_sweep_confirm)) {
      asset_center_sweep_notice(list(tone = "warning", title = "Bestätigung fehlt",
        copy = "Der Sammellauf ruft ab, veröffentlicht und schreibt die Bewertungen ohne Einzelvorschau. Dafür das Häkchen darüber setzen, dann erneut starten."))
      return()
    }
    # Ein offener Einzelentwurf und der Sammellauf teilen sich denselben
    # Bewertungsdienst. Liefe beides, bewertete der Lauf den Entwurf des Assets
    # mit weg, ohne dass es jemand saehe.
    if (!is.null(asset_center_refresh_pending())) {
      asset_center_sweep_notice(list(tone = "warning", title = "Offener Bewertungsentwurf",
        copy = "Oben steht noch ein Bewertungsentwurf offen. Erst „Bewertung abschließen“ oder „Entwurf verwerfen“, dann startet der Sammellauf."))
      return()
    }
    lock <- paste0("run_sweep", format(Sys.time(), "%Y%m%d%H%M%S", tz = "UTC"))
    if (is.null(refresh_all_store) || refresh_all_background_busy() || !isTRUE(tryCatch(refresh_all_store$acquire(lock, "app_sweep"), error = function(error) FALSE))) {
      asset_center_sweep_notice(list(tone = "warning", title = "Ein Lauf läuft",
        copy = refresh_all_holder_copy("Der Sammellauf lässt sich danach starten.")))
      return()
    }
    asset_center_sweep_lock <<- lock
    asset_center_sweep_notice(NULL)
    asset_center_sweep$running <- TRUE
    asset_center_sweep$resume_at <- NULL
  })
  shiny::observeEvent(input$asset_center_sweep_stop, {
    asset_center_sweep$running <- FALSE
    asset_center_sweep$resume_at <- NULL
    asset_center_sweep_release()
  })
  shiny::observe({
    if (!isTRUE(asset_center_sweep$running)) return()
    # Drei Sekunden Abstand zwischen zwei Assets. Der Abstand ist der Grund,
    # warum die Quelle den Lauf ueberhaupt durchlaesst: Sie weist Abrufe ab,
    # die dicht aufeinander folgen (#283).
    shiny::invalidateLater(3000L)
    resume_at <- asset_center_sweep$resume_at
    if (!is.null(resume_at) && Sys.time() < resume_at) return()
    shiny::isolate({
      if (!is.null(asset_center_sweep_lock)) tryCatch(refresh_all_store$heartbeat(asset_center_sweep_lock), error = function(error) NULL)
      tryCatch(asset_center_sweep_step(), error = function(error) {
        asset_center_sweep$running <- FALSE
        asset_center_sweep_notice(list(tone = "error", title = "Sammellauf abgebrochen",
          copy = pl_error_text_v1(spotcore::desktop_product_safe_error_code_v1(error))))
      })
      if (!isTRUE(asset_center_sweep$running)) asset_center_sweep_release()
    })
  })
  # „Alles aktualisieren“ (#463, Stufe 1): FIFO, Sammellauf, Tageshistorie, Snapshot, Staende - eine Bestaetigung.
  # Die Schritte sind die vorhandenen Kerne; der Sammellauf laeuft ueber seinen eigenen Beobachter weiter.
  refresh_all_service <- tryCatch(new_data_portfolio_snapshot_service_v1(project_root, runtime$context), error = function(error) NULL)
  refresh_all_require <- function() if (is.null(refresh_all_service)) stop("data_portfolio_snapshot_service_invalid", call. = FALSE)
  # „Alles aktualisieren“ laeuft seit rc.315 (#510) als eigener Prozess (scripts/desktop_refresh_all.R) mit den Bausteinen aus
  # data_refresh_all_deps_v1.R. Diese Karte startet ihn, zeigt seinen Stand und bittet um Anhalten; ein Wechsel in eine andere
  # App oder Neuladen schadet ihm nicht mehr.
  refresh_all_store <- tryCatch(data_refresh_all_store_v1(runtime_data_space_path(runtime$context)), error = function(error) NULL)
  refresh_all_background_busy <- function() !is.null(refresh_all_store) && is.list(tryCatch(refresh_all_store$holder(), error = function(error) NULL))
  # Wer gerade sperrt, beim Namen (rc.365, #516): Zeitplan, Momentaufnahme, Sammellauf oder Wartung - statt pauschal „Alles aktualisieren“.
  refresh_all_holder_copy <- function(then) {
    holder <- if (is.null(refresh_all_store)) NULL else tryCatch(refresh_all_store$holder(), error = function(error) NULL)
    paste0("Gerade läuft ", if (is.list(holder)) data_refresh_all_holder_text_v1(holder) else "„Alles aktualisieren“", ". ", then)
  }
  # Taeglich von selbst (rc.316, #510): derselbe Lauf, gestartet von einem systemd-Timer des Benutzers.
  refresh_all_schedule <- if (is.null(refresh_all_store)) NULL else tryCatch(data_refresh_all_schedule_v1(project_root, runtime, refresh_all_store), error = function(error) NULL)
  data_refresh_all_schedule_server_v1(input, output, session, refresh_all_schedule, now_utc)
  # Nach Stammdatenpflege die Datenbasis neu veroeffentlichen, nur wenn nichts Rechnungsrelevantes offen ist (rc.332, #422).
  data_basis_names_server_v1(input, output, session, refresh_all_service, refresh_all_store, now_utc)
  refresh_all <- data_refresh_all_server_v1(input, output, session, list(
    store = refresh_all_store,
    today = function() format(Sys.Date(), "%Y-%m-%d"),
    stands = function(as_of) { refresh_all_require(); refresh_all_service$stands(as_of) },
    durations_read = function() if (is.null(user_settings_service)) list() else user_settings_service$durations_read(),
    blocked = function() {
      if (is.null(refresh_all_store)) return("Der Speicherort für den Stand des Laufs ist nicht lesbar.")
      # Ein zweiter Lauf startete und beendete sich sofort; die Karte meldete dann nur „refresh_all_start_timeout“ (rc.365, #516).
      if (refresh_all_background_busy()) return(refresh_all_holder_copy("Ihn abwarten, dann erneut starten."))
      if (isTRUE(asset_center_sweep$running))
        return("Im Reiter Marktdaten läuft bereits ein Sammellauf. Ihn abwarten oder anhalten, dann erneut starten.")
      if (!is.null(asset_center_refresh_pending()))
        return("Im Reiter Marktdaten steht ein Bewertungsentwurf offen. Erst „Bewertung abschließen“ oder „Entwurf verwerfen“, dann erneut starten.")
      NULL
    },
    spawn = function(retry_gaps) data_refresh_all_spawn_v1(project_root, runtime, refresh_all_store, retry_gaps),
    # Nach dem Lauf: Buchungen, FIFO-Stand, Tageshistorie und Abschluss neu lesen, damit die Seite den neuen Stand zeigt.
    on_finished = function(state) {
      tryCatch(invisible(refresh_realized_state()), error = function(error) NULL)
      tryCatch(invisible(refresh_activity_catalog()), error = function(error) NULL)
      tryCatch(invisible(portfolio_history$read()), error = function(error) NULL)
      tryCatch(invisible(load_published_workflow()), error = function(error) NULL)
    }))
  # Block links (#540): Stand direkt aus Sperre, Stand und Zeitplan; veroeffentlicht fuer die anderen Apps, wenn niemand sperrt oder
  # der Sammellauf dieser Sitzung sperrt - waehrend eines Hintergrundlaufs veroeffentlicht nur dieser.
  asset_center_sweep_progress <- function() shiny::isolate(if (isTRUE(asset_center_sweep$running))
    list(done = length(asset_center_sweep$results), total = length(asset_center_sweep$queue)) else NULL)
  activity_publisher <- if (is.null(refresh_all_store)) NULL else tryCatch(data_activity_publisher_v1(project_root, runtime$context,
    function() data_activity_status_v1(refresh_all_store, asset_center_sweep_progress())), error = function(error) NULL)
  desktop_activity_server_v1(input, output, session, data_activity_source_v1(refresh_all_store, activity_publisher,
    asset_center_sweep_progress, function() asset_center_sweep_lock))
  desktop_help_server_v1(input, output, session, project_root, "data")
  # Reiter „Programm“ (#562, #586): Version, „Neu in dieser Version“ (einmal nach einem Update auch oben), Browser der Installation.
  data_program_server_v1(input, output, session, project_root, if (is.character(runtime$home) && length(runtime$home) == 1L) runtime$home else "")
  # Ein Regelmodul fehlt, ist ueberholt oder seit der Wahl in seinen Regeln geaendert (#527): Die Auswahl klappt dann von selbst auf.
  tax_module_needed <- shiny::reactive({
    rows <- tax_model()$readiness
    length(rows) > 0L && any(vapply(rows, function(row) as.character(row$status) %in%
      c("no_plugin", "plugin_version_stale", "plugin_rules_changed", "unsupported_mode"), logical(1L)))
  })
  shiny::observeEvent(tax_module_needed(), if (isTRUE(tax_module_needed())) session$sendCustomMessage("pl_open_tax_module", list()))
  # Anlaesse der Karten "nur bei Problemen" (#492): jede erscheint von selbst, solange ihr Anlass besteht.
  statement_failed <- shiny::reactiveVal(FALSE)
  # Einmal abgebrochen, bleiben die Einzelschritte fuer die Sitzung stehen - dort wird weiter untersucht.
  shiny::observe(if (identical(statement_guided_result()$tone, "error")) statement_failed(TRUE))
  data_visibility_server_v1(output, list(
    setup = function() isTRUE(need_setup()),
    portfolio = function() {
      catalog <- asset_center_catalog()
      is.list(catalog) && !length(Filter(function(row) !identical(row$status, "archived"), catalog$portfolios))
    },
    tax_setup = function() identical(asset_center_tax_state(), "not_initialized"),
    tax_module = function() isTRUE(tax_module_needed()),
    history_halted = function() isTRUE(refresh_all$halted()),
    market_setup_failed = function() isTRUE(market_setup_failed()),
    statement_failed = function() isTRUE(statement_failed()),
    action_failed = function() identical(state()$tone, "error"),
    cash_recovery = function() length(cash_catalog()$recovery_candidates) > 0L,
    inherited_rates = function() NROW(data_tax_inherited_frame_v1(tax_model(), tax_labels())) > 0L,
    csv_resume = function() length(activity_csv_resumable()$candidates) > 0L,
    scale_resume = function() length(scale_pending()$candidates) > 0L))
  # Unterbrochene CSV-Importe und Skalenanpassungen: einmal pruefen, wenn die Seite steht (Festlegung 23.10.2026). Je ein
  # kurzer Leseaufruf; offene Vorgaenge stehen danach gleich in der Auswahl der Karte.
  session$onFlushed(function() {
    tryCatch(activity_csv_resume_offer(data_asset_activity_csv_resumable_v1(activity_csv_center, runtime$context)), error = function(error) NULL)
    tryCatch(scale_resume_offer(data_asset_quantity_scale_pending_v1(scale_center, runtime$context)), error = function(error) NULL)
  }, once = TRUE)
  # Der Schalter gilt fuer alle Assets zugleich: Es geht um den Umgang mit
  # Quellluecken, nicht um ein einzelnes Papier. Das Umstellen aendert den
  # Richtlinien-Fingerabdruck; der Bewertungsstand rechnet die betroffenen
  # Bereiche beim naechsten Lauf neu (#368, 28.09.2026).
  intraday_settings <- tryCatch(new_data_intraday_snapshot_service_v1(project_root, runtime$context),
    error = function(error) NULL)
  # Snapshot zu anderem Stichtag und gleichzeitige Abrufe der Momentaufnahme (rc.313; bis rc.312 im Cockpit).
  snapshot_other_area <- data_snapshot_publish_server_v1(input, output, session, refresh_all_service, intraday_settings, now_utc)
  gap_carry_notice <- shiny::reactiveVal(NULL)
  gap_carry_value <- shiny::reactiveVal(NULL)
  gap_carry_current <- function() {
    stored <- gap_carry_value()
    if (!is.null(stored)) return(stored)
    value <- if (is.null(intraday_settings)) FALSE else
      tryCatch(intraday_settings$carry_across_blocked(), error = function(error) FALSE)
    gap_carry_value(value); value
  }
  output$asset_center_gap_carry <- shiny::renderUI({
    notice <- gap_carry_notice()
    if (is.null(intraday_settings)) return(portelyra_status_panel("Einstellung nicht verfügbar",
      "Der Bewertungsstand ist nicht lesbar.", tone = "error"))
    shiny::tagList(
      shiny::p(class = "pl-section-copy", paste(
        "Ein gesperrter Tag bleibt immer ohne Wert - etwa solange ein Abruf dafür offen ist.",
        "Hier steht nur, ob die Sperre auch die Tage danach trifft.",
        "Ohne Häkchen verliert die Reihe ab dem gesperrten Tag ihren Vorgänger und bleibt leer,",
        "bis die Quelle wieder einen Kurs liefert.")),
      shiny::checkboxInput("asset_center_gap_carry_choice",
        "Vorgänger über einen gesperrten Tag hinweg behalten", gap_carry_current()),
      shiny::actionButton("asset_center_gap_carry_save", "Einstellung speichern", class = "btn-default"),
      if (is.null(notice)) NULL else portelyra_status_panel(notice$title, notice$copy, tone = notice$tone))
  })
  shiny::observeEvent(input$asset_center_gap_carry_save, {
    if (is.null(intraday_settings)) return(invisible(NULL))
    wanted <- isTRUE(input$asset_center_gap_carry_choice)
    result <- tryCatch(intraday_settings$set_carry_across_blocked(wanted,
      format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ")), error = function(error) NULL)
    if (is.null(result)) {
      gap_carry_notice(list(tone = "error", title = "Einstellung nicht gespeichert",
        copy = "Der Bewertungsstand ist nicht schreibbar. Es wurde nichts geändert."))
      return(invisible(NULL))
    }
    gap_carry_value(result)
    gap_carry_notice(list(tone = "positive", title = "Einstellung gespeichert",
      copy = if (result)
        "Ein gesperrter Tag unterbricht die Reihe nicht mehr. Die betroffenen Bereiche werden beim nächsten Lauf neu gerechnet."
      else
        "Ein gesperrter Tag unterbricht die Reihe wieder. Die betroffenen Bereiche werden beim nächsten Lauf neu gerechnet."))
  })
  output$asset_center_sweep_state <- shiny::renderUI({
    notice <- asset_center_sweep_notice()
    panel <- if (is.null(notice)) NULL else portelyra_status_panel(notice$title, notice$copy, tone = notice$tone)
    if (!isTRUE(asset_center_sweep$prepared)) return(panel)
    total <- length(asset_center_sweep$queue)
    done <- length(asset_center_sweep$results)
    resume_at <- asset_center_sweep$resume_at
    completed <- length(Filter(function(row) identical(row$status, "completed"), asset_center_sweep$results))
    tone <- if (isTRUE(asset_center_sweep$running)) "neutral" else if (done >= total && total > 0L) "positive" else "warning"
    title <- if (!is.null(resume_at))
        paste0("Quelle bremst - naechster Versuch um ", format(resume_at, "%H:%M:%S"))
      else if (isTRUE(asset_center_sweep$running)) paste0("Laeuft - ", done, " von ", total, " Assets")
      else if (done == 0L) paste0(total, " Assets vorbereitet - noch nicht gestartet")
      else paste0("Angehalten nach ", done, " von ", total, " Assets")
    shiny::tagList(
      panel,
      portelyra_status_panel(title, paste0(completed, " bewertet und geschrieben · ",
        done - completed, " uebersprungen oder zurueckgestellt · ", total - done, " offen. ",
        "Ein erneuter Lauf holt nur noch das Fehlende."), tone = tone),
      if (length(asset_center_sweep$results)) shiny::div(class = "pl-table-wrap",
        style = "max-height:320px;overflow:auto", shiny::tableOutput("asset_center_sweep_table")))
  })
  output$asset_center_sweep_table <- shiny::renderTable({
    rows <- rev(asset_center_sweep$results)
    if (!length(rows)) return(NULL)
    data.frame(
      Asset = vapply(rows, function(row) as.character(row$asset_name), character(1L)),
      Ergebnis = vapply(rows, function(row) switch(as.character(row$status),
        completed = "bewertet", skipped = "uebersprungen", deferred = "zurueckgestellt", "abgebrochen"),
        character(1L)),
      Details = vapply(rows, function(row) {
        if (identical(row$status, "completed"))
          # Der bewertete Zeitraum gehoert in die Zeile: Bei vielen Assets mit je
          # eigenem Beginn ist die Tageszahl allein nicht nachpruefbar (#283).
          paste0(format(as.Date(row$from), "%d.%m.%Y"), " – ", format(as.Date(row$until), "%d.%m.%Y"),
                 " · ", asset_center_valuation_numbers_copy(row$numbers), " · ",
                 data_market_valuation_quality_label_v1(row$quality),
                 # Warum der Zeitraum spaeter beginnt als gewuenscht, soll nicht
                 # geraten werden muessen (Festlegung 25.09.2026, #283).
                 if (is.character(row$listed_since) && length(row$listed_since) == 1L &&
                     !is.na(row$listed_since))
                   paste0(" · Erstnotiz laut Quelle ", format(as.Date(row$listed_since), "%d.%m.%Y")) else "")
        else if (!is.null(row$reason)) as.character(row$reason)
        else {
          reason <- asset_center_fetch_reason(row$code)
          if (nzchar(reason)) reason
          else paste0("bei „", as.character(row$step), "“ · ", as.character(row$code))
        }
      }, character(1L)),
      stringsAsFactors = FALSE, check.names = FALSE)
  }, striped = TRUE, spacing = "xs", width = "100%")
  action_feedback$observe('refresh', input$asset_center_refresh_execute, {
    if (refresh_all_background_busy()) {
      state(list(tone = "warning", title = "Ein Lauf läuft",
        copy = refresh_all_holder_copy("Der Einzelabruf lässt sich danach ausführen.")))
      return()
    }
    planned <- asset_center_refresh_plan()
    if (is.null(planned)) {
      state(list(tone = "warning", title = "Zuerst planen", copy = "Bitte zuerst „Aktualisierung planen“ ausführen; ohne Plan erfolgt kein Abruf."))
      return()
    }
    outcome <- asset_center_chain_run(input$asset_center_asset, planned)
    step <- outcome$step
    fetched <- outcome$fetched
    fetched_fx <- outcome$fetched_fx
    asset_center_refresh_plan(NULL)
    if (identical(outcome$status, "failed")) {
      asset_center_refresh_pending(NULL)
      # Eine Abweisung durch die Quelle ist kein Produktfehler und keine Ratlosigkeit:
      # Sie sagt, dass es spaeter wieder geht (22.09.2026, #283).
      reason <- asset_center_fetch_reason(outcome$code)
      state(list(tone = "error", title = paste("Aktualisierung abgebrochen bei:", step),
        copy = paste0(fetched, " Kurs- und ", fetched_fx, " Wechselkursbereiche waren bereits veröffentlicht und bleiben erhalten. ",
          if (nzchar(reason)) paste0(reason, " ") else "",
          pl_error_text_v1(outcome$code))))
    } else {
      asset_center_refresh_pending(outcome)
      numbers <- asset_center_valuation_numbers(outcome$summary, outcome$detail)
      state(list(tone = "neutral", title = "Vorschau · noch nichts bewertet",
        copy = paste0(outcome$fetched, " Kurs- und ", outcome$fetched_fx, " Wechselkursbereiche veröffentlicht · ",
          if (outcome$resolved_fx > 0L) paste0(outcome$resolved_fx, " offene Wechselkurs-Versuche aufgelöst · ") else "",
          if (outcome$bound_closures > 0L) paste0(outcome$bound_closures, " Schließtage aus dem Kursverlauf übernommen · ") else "",
          "Entwurf ", format(as.Date(outcome$valued_from), "%d.%m.%Y"), " bis ", format(as.Date(outcome$until), "%d.%m.%Y"),
          if (!identical(outcome$valued_from, outcome$requested_from)) ", davor ist das Asset nicht notiert" else "",
          " · ", asset_center_valuation_numbers_copy(numbers), asset_center_valuation_reason(outcome$detail),
          " Bitte den Kursverlauf darunter prüfen; erst „Bewertung abschließen“ schreibt sie.")))
    }
  })
  # Zahlen der Bewertung, je Tag und ueberschneidungsfrei. Die Summe der
  # Einzelzaehler taugt nicht: Ein Wochenende ist bei einer Auslandsaktie zugleich
  # kursseitig und wechselkursseitig geschlossen und wurde doppelt gezaehlt. Ausserdem ist ein geschlossener
  # Boersentag etwas anderes als ein Ersatzwert fuer eine echte Quelllueecke:
  # ersteres ist erwartet, letzteres ist die Qualitaetsfrage (#283, 21.09.2026).
  asset_center_valuation_numbers <- function(row, detail = NULL) asset_center_chain$valuation_numbers(row, detail)
  # Tagesliste des Entwurfs: je Tag eine Farbe. Gruen bedeutet nativer Kurs und
  # nativer Wechselkurs, Gelb einen geschlossenen Handelstag, Rot einen Ersatzwert
  # fuer eine echte Quelllueecke, Grau einen offenen Tag (#283, 21.09.2026).
  asset_center_valuation_day_kind <- function(day) {
    price <- if (is.null(day$price_basis)) "" else as.character(day$price_basis)
    rate <- if (is.null(day$fx_basis)) "identity" else as.character(day$fx_basis)
    if (is.null(day$target_decimal) || identical(day$valuation_status, "incomplete")) "open"
    else if (isTRUE(day$substitution_used)) "substituted"
    else if (!identical(price, "observed")) "calendar"
    # Der Kurs steht, nur der Devisenkurs des Tages fehlt: eigene Farbe, sonst
    # sieht ein vollstaendiger 24/7-Verlauf nach Luecken aus (26.09.2026, #283).
    else if (!rate %in% c("identity", "observed")) "calendar_rate"
    else "native"
  }
  ASSET_CENTER_DAY_STYLE <- list(
    native = list(colour = "#1c7a3e", label = "nativ"),
    calendar = list(colour = "#b8860b", label = "geschlossener Handelstag · fortgeschrieben"),
    calendar_rate = list(colour = "#8a6d1f", label = "nativer Kurs · Wechselkurs fortgeschrieben"),
    substituted = list(colour = "#b3261e", label = "Ersatzwert für Quelllücke"),
    open = list(colour = "#6b7280", label = "offen · kein Wert"))
  asset_center_valuation_day_table <- function(detail, show_all = FALSE) {
    if (is.null(detail) || !length(detail)) return(shiny::p(class = "pl-field-hint", "Keine Tageszeilen im Entwurf."))
    kinds <- vapply(detail, asset_center_valuation_day_kind, character(1L))
    # Bei langen Zeitraeumen bleiben die auffaelligen Tage vollstaendig sichtbar;
    # die nativen werden gezaehlt statt gelistet, sonst wird die Seite unbedienbar.
    # Wer alle Tage sehen will, sagt es ausdruecklich: Eine Liste nur mit
    # fortgeschriebenen Tagen liest sich wie "immer fortgeschrieben"
    # (Festlegung 22.09.2026, #283).
    full <- isTRUE(show_all) || length(detail) <= 800L
    shown <- if (full) seq_along(detail) else which(kinds != "native")
    omitted <- length(detail) - length(shown)
    rows <- lapply(shown, function(index) {
      day <- detail[[index]]; style <- ASSET_CENTER_DAY_STYLE[[kinds[[index]]]]
      value <- if (is.null(day$target_decimal)) "—" else as.character(day$target_decimal)
      shiny::tags$tr(
        shiny::tags$td(format(as.Date(as.character(day$date)), "%d.%m.%Y")),
        shiny::tags$td(style = "text-align:right", value),
        shiny::tags$td(shiny::tags$span(style = paste0("color:", style$colour, ";font-weight:700"), "● "), style$label))
    })
    shiny::tagList(
      if (omitted > 0L) portelyra_status_panel("Gefilterte Ansicht",
        paste0(omitted, " Tage mit nativem Kurs sind ausgeblendet; gelistet sind nur die ",
          length(shown), " fortgeschriebenen, ersetzten und offenen Tage. Häkchen setzen, um alle Tage zu sehen."),
        tone = "neutral") else NULL,
      shiny::div(class = "pl-table-wrap", style = "max-height:360px;overflow:auto",
        shiny::tags$table(class = "table table-condensed",
          shiny::tags$thead(shiny::tags$tr(shiny::tags$th("Tag"), shiny::tags$th(style = "text-align:right", "EUR je Einheit"), shiny::tags$th("Herkunft"))),
          shiny::tags$tbody(rows))))
  }
  # Fortgeschrieben heisst nicht immer "Kurs fehlt". Steht der Kurs und fehlt nur
  # der Devisenkurs des Tages, gehoert das so gesagt - sonst sieht ein
  # vollstaendiger 24/7-Kursverlauf nach vielen Luecken aus (#283).
  asset_center_valuation_carry_copy <- function(numbers) {
    price <- if (is.null(numbers$calendar_price)) NULL else as.integer(numbers$calendar_price)
    rate <- if (is.null(numbers$calendar_rate)) NULL else as.integer(numbers$calendar_rate)
    if (is.null(price) || is.null(rate) || (price + rate) != as.integer(numbers$calendar))
      return(paste0(numbers$calendar, " an geschlossenen Handelstagen fortgeschrieben"))
    if (rate == 0L) return(paste0(price, " an geschlossenen Handelstagen fortgeschrieben"))
    if (price == 0L) return(paste0(rate, " Tage mit nativem Kurs, aber fortgeschriebenem Wechselkurs (Devisenmarkt geschlossen)"))
    paste0(price, " an geschlossenen Handelstagen fortgeschrieben, ", rate,
           " weitere nur im Wechselkurs fortgeschrieben (Devisenmarkt geschlossen)")
  }
  asset_center_valuation_numbers_copy <- function(numbers) paste0(
    numbers$native, " Tage mit nativem Kurs, ", asset_center_valuation_carry_copy(numbers), ", ",
    numbers$substituted, " Ersatzwerte, ", numbers$open, " offen.",
    # Splitbereinigte Tage sind keine Ersatzwerte, aber auch nicht der Kurs, der
    # damals an der Tafel stand. Beides gehoert gesagt (22.09.2026, #283).
    if (!is.null(numbers$adjusted) && numbers$adjusted > 0L)
      paste0(" Davon ", numbers$adjusted, " splitbereinigt: Wegen einer Kapitalmaßnahme gilt der bereinigte Kurs der Quelle, damit die Reihe über den Split hinweg vergleichbar bleibt.") else "")
  # "Alles offen" hat fast immer einen benennbaren Grund. Ohne ihn sucht der
  # Nutzer beim Kurs, obwohl die Sperre vom Wechselkurs kommt.
  asset_center_valuation_reason <- function(detail) {
    if (is.null(detail) || !length(detail)) return("")
    reason <- function(key, value) sum(vapply(detail, function(day) identical(as.character(day[[key]]), value), logical(1L)))
    # Der erste Tag eines Zeitraums kann vor dem ersten Kurs liegen; dann gibt es
    # nichts fortzuschreiben. Das ist kein Mangel der Daten, sondern die Wahl des
    # Beginns — und es sollte nicht wie eine Luecke aussehen (23.09.2026).
    if (reason("price_basis", "no_predecessor") > 0L && reason("price_basis", "no_predecessor") == sum(vapply(detail, function(day) is.null(day$target_decimal) || identical(day$valuation_status, "incomplete"), logical(1L))))
      return(paste0(" Offen ist allein der Beginn des Zeitraums: Er liegt vor dem ersten verfügbaren Kurs, es gibt also keinen Vorgängerwert zum Fortschreiben. Ein späterer Beginn schließt die Lücke."))
    if (reason("price_basis", "blocked_corporate_action") > 0L)
      return(paste0(" Gesperrt durch eine Kapitalmaßnahme, für die die Quelle keinen bereinigten Kurs liefert: ",
        "Vor- und Nachsplitkurse sind ohne Bereinigung nicht vergleichbar."))
    if (reason("fx_basis", "unknown_fx_attempt") > 0L)
      return(" Gesperrt durch einen Wechselkurs-Versuch mit unbekanntem Ausgang: Solange er weder veröffentlicht noch quittiert ist, bleibt jeder Fremdwährungstag ungewertet.")
    if (reason("fx_basis", "pair_missing") > 0L)
      return(" Das benötigte Währungspaar fehlt; bitte im FX-Abschnitt ein Paar suchen und übernehmen.")
    if (reason("price_basis", "not_requested") > 0L)
      return(" Für einen Teil des Zeitraums wurden noch keine Kurse abgerufen; „Prüfen, was fehlt“ plant sie.")
    ""
  }
  output$asset_center_refresh_preview <- shiny::renderUI({
    pending <- asset_center_refresh_pending()
    if (is.null(pending)) return(NULL)
    numbers <- asset_center_valuation_numbers(pending$summary, pending$detail)
    shiny::tagList(
      portelyra_status_panel(if (isTRUE(pending$view_only)) "Kursverlauf der Bewertung · nur Ansicht" else "Kursverlauf des Entwurfs · noch nicht geschrieben",
        paste0(format(as.Date(pending$valued_from), "%d.%m.%Y"), " bis ", format(as.Date(pending$until), "%d.%m.%Y"),
          " · ", asset_center_valuation_numbers_copy(numbers)),
        tone = if (numbers$open > 0L) "warning" else if (numbers$substituted > 0L) "warning" else "neutral"),
      shiny::plotOutput("asset_center_refresh_preview_plot", height = "320px"),
      shiny::tags$details(shiny::tags$summary("Tagesliste des Entwurfs · nativ, fortgeschrieben, ersetzt"),
        shiny::checkboxInput("asset_center_day_all", "Auch die Tage mit nativem Kurs listen", FALSE),
        shiny::uiOutput("asset_center_day_table")),
      if (isTRUE(pending$view_only))
        shiny::div(class = "pl-editor-actions",
          shiny::actionButton("asset_center_refresh_discard", "Ansicht schließen", class = "btn-default"))
      else shiny::div(class = "pl-editor-actions",
        shiny::actionButton("asset_center_refresh_complete", "Bewertung abschließen", class = "btn-primary"),
        shiny::actionButton("asset_center_refresh_discard", "Entwurf verwerfen · Kurse bleiben erhalten", class = "btn-default")))
  })
  output$asset_center_day_table <- shiny::renderUI({
    pending <- asset_center_refresh_pending(); if (is.null(pending)) return(NULL)
    asset_center_valuation_day_table(pending$detail, isTRUE(input$asset_center_day_all))
  })
  output$asset_center_refresh_preview_plot <- shiny::renderPlot({
    pending <- asset_center_refresh_pending()
    rows <- if (is.null(pending)) list() else pending$detail
    values <- vapply(rows, function(row) {
      value <- suppressWarnings(as.numeric(row$target_decimal)); if (length(value) != 1L || is.na(value)) NA_real_ else value
    }, numeric(1L))
    dates <- as.Date(vapply(rows, function(row) as.character(row$date), character(1L)))
    keep <- !is.na(values)
    if (!any(keep)) { plot.new(); title(main = "Kein bewerteter Tag im Entwurf"); return(invisible(NULL)) }
    kinds <- vapply(rows, asset_center_valuation_day_kind, character(1L))
    plot(dates[keep], values[keep], type = "l", col = "#4b5563", xlab = "", ylab = "EUR je Einheit",
      main = "Bewertungsentwurf in EUR · grün nativ, gelb fortgeschrieben, rot Ersatzwert")
    for (kind in c("native", "calendar_rate", "calendar", "substituted")) {
      marked <- keep & kinds == kind
      if (any(marked)) points(dates[marked], values[marked], pch = 20, col = ASSET_CENTER_DAY_STYLE[[kind]]$colour)
    }
  })
  action_feedback$observe('refresh', input$asset_center_refresh_complete, {
    pending <- asset_center_refresh_pending()
    if (is.null(pending)) {
      state(list(tone = "warning", title = "Kein Entwurf", copy = "Es liegt kein Bewertungsentwurf vor. Bitte zuerst „Prüfen, was fehlt“ und den Lauf ausführen."))
      return()
    }
    outcome <- tryCatch(list(status = "completed", valuation = asset_center_valuation_service$complete(pending$review, TRUE)),
      error = function(error) list(status = "failed", code = spotcore::desktop_product_safe_error_code_v1(error)))
    if (identical(outcome$status, "failed")) {
      state(list(tone = "error", title = "Bewertung nicht geschrieben",
        copy = paste0("Der Entwurf war nicht mehr gültig; abgerufene Kurse bleiben erhalten. Bitte „Prüfen, was fehlt“ erneut ausführen. (Code: ", outcome$code, ")")))
      asset_center_refresh_pending(NULL)
      return()
    }
    numbers <- asset_center_valuation_numbers(pending$summary, pending$detail)
    asset_center_refresh_pending(NULL)
    state(list(tone = if (identical(outcome$valuation$valuation_status, "complete")) "positive" else "warning",
      title = "Bewertung aktualisiert",
      copy = paste0("Bewertung bis ", format(as.Date(pending$until), "%d.%m.%Y"), " · ",
        if (!identical(pending$valued_from, pending$requested_from))
          paste0("bewertet ab ", format(as.Date(pending$valued_from), "%d.%m.%Y"), ", davor ist das Asset nicht notiert · ") else "",
        data_market_valuation_quality_label_v1(outcome$valuation$valuation_status),
        " · ", asset_center_valuation_numbers_copy(numbers))))
  })
  # Kurve und Tagesliste waren nur waehrend des Laufs zu sehen und danach weg. Die
  # Ansicht bereitet denselben Entwurf noch einmal vor - lesend, ohne Abruf und
  # ohne Schreiben - und zeigt ihn erneut (#283).
  action_feedback$observe('refresh', input$asset_center_valuation_view, {
    safe({
      # Ohne aufgefrischten Zuordnungseditor liefert die Aufloesung kein Listing,
      # und der Entwurf meldet jeden Tag als offen. Die Kette frischt ihn beim
      # Aufloesen des Abrufziels mit auf; die Ansicht muss das selbst tun
      # (22.09.2026, #283).
      invisible(asset_center_refresh(shiny::isolate(input$asset_center_asset)))
      # Denselben Weg gehen wie die Kette: Erst das Abrufziel aufloesen, dann
      # bewerten. Ohne diesen Schritt fehlte dem Entwurf das Listing und jeder Tag
      # galt als offen (22.09.2026, #283).
      method <- asset_center_selected_method()
      if (identical(method, "external_market")) {
        asset_center_require_market(TRUE)
        invisible(asset_center_refresh_target())
      }
      resolved_fx <- asset_center_resolve_open_fx()
      asset_center_valuation_workflow$invalidate()
      inventory <- asset_center_valuation_inventory()
      rows <- Filter(function(row) identical(row$asset_ref, input$asset_center_asset), inventory$rows)
      if (length(rows) != 1L) stop("desktop_market_valuation_selection_invalid", call. = FALSE)
      until <- as.character(min(as.Date(input$asset_center_period_end), Sys.Date() - 1L))
      request <- list(targets = asset_center_valuation_resolve(rows), execution_ref = NULL,
        start_date = as.character(input$asset_center_period_start), end_date = until,
        valuation_policy = list(mode = "last_valid", max_age_days = NULL, age_unit = "calendar_days"),
        target_currency = "EUR", use_rules = identical(method, "external_market"), use_saved_calendars = FALSE, max_age_days = 366L,
        market_exceptions = structure(list(), names = character()), fx_exceptions = structure(list(), names = character()),
        simple_absence_policy = FALSE,
        use_trade_prices = identical(method, "manual") && identical(asset_center_manual_source(), "trade_prices"),
        use_manual_prices = identical(method, "manual") && identical(asset_center_manual_source(), "own_entries"))
      review <- asset_center_valuation_service$prepare(request)
      detail <- tryCatch(asset_center_valuation_service$detail(1L)$rows, error = function(error) list())
      list(view_only = TRUE, fetched = 0L, fetched_fx = 0L, resolved_fx = resolved_fx, bound_closures = 0L,
           review = review, detail = detail, valued_from = request$start_date,
           requested_from = request$start_date, until = until,
           summary = if (length(review$rows)) review$rows[[1L]] else NULL)
    }, function(value) {
      asset_center_refresh_pending(value)
      numbers <- asset_center_valuation_numbers(value$summary, value$detail)
      state(list(tone = "neutral", title = "Bewertung angesehen · nichts abgerufen, nichts geschrieben",
        copy = paste0(format(as.Date(value$valued_from), "%d.%m.%Y"), " bis ", format(as.Date(value$until), "%d.%m.%Y"),
          " · ", if (value$resolved_fx > 0L) paste0(value$resolved_fx, " offene Wechselkurs-Versuche aufgelöst · ") else "",
          asset_center_valuation_numbers_copy(numbers), asset_center_valuation_reason(value$detail))))
    })
  })
  # Snapshot-Test: Holt den tagesfrischen Kurs des Assets und des benoetigten
  # Waehrungspaares. Liefert die Quelle keinen laufenden Kurs, gilt der jueengste
  # abgeschlossene Tagesschluss - gekennzeichnet, nie stillschweigend
  # (Festlegung 22.09.2026, #373).
  asset_center_snapshot_probe <- shiny::reactiveVal(NULL)
  asset_center_quote_row <- function(label, symbol, currency, result) {
    # Der Name der Quelle neben dem eigenen Assetnamen macht eine Verwechslung
    # sofort sichtbar.
    quelle <- if (is.character(result$instrument_name) && length(result$instrument_name) == 1L && nzchar(result$instrument_name))
      paste0(label, " · Quelle meldet: ", result$instrument_name,
        if (is.character(result$instrument_type) && length(result$instrument_type) == 1L && nzchar(result$instrument_type))
          paste0(" (", result$instrument_type, ")") else "")
      else label
    basis <- label
    label <- quelle
    live <- result$live_session
    if (is.list(live) && !is.null(live$close_decimal))
      return(list(quelle = label, basis = basis, symbol = symbol, waehrung = currency,
        wert = as.character(live$close_decimal), stand = as.character(live$observed_at_utc),
        art = "laufende Sitzung · Zwischenstand"))
    day <- if (is.null(result$last_observed_date)) NA_character_ else as.character(result$last_observed_date)
    # Ein Tagesbalken des heutigen Tages ist noch nicht abgeschlossen. Bei einem
    # 24/7-Markt beginnt er um 00:00 und traegt deshalb schon jetzt das heutige
    # Datum; ihn "Tagesschluss" zu nennen waere falsch (22.09.2026, #373).
    running <- !is.na(day) && identical(day, as.character(Sys.Date()))
    list(quelle = label, basis = basis, symbol = symbol, waehrung = currency,
      wert = if (is.null(result$last_close_decimal)) "—" else as.character(result$last_close_decimal),
      stand = if (is.na(day)) "—" else day,
      art = if (running) "laufender Tag · noch nicht abgeschlossen" else "letzter abgeschlossener Tagesschluss")
  }
  action_feedback$observe('refresh', input$asset_center_snapshot_quote, {
    safe({
      asset_center_require_market(TRUE)
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      scope <- data_provider_mapping_editor_resolve_quote_scope_v1(asset_center_provider_editor, runtime$context, input$asset_center_mapping)
      quote_scope <- scope; quote_scope$catalog_fingerprint <- NULL
      window_start <- as.character(Sys.Date() - 6L); window_end <- as.character(Sys.Date())
      preview <- asset_center_provider_probe_service$preview(quote_scope, window_start, window_end, now_utc())
      result <- asset_center_provider_probe_service$execute(preview, TRUE)
      rows <- list(asset_center_quote_row(data_asset_center_selected_v1(asset_center_catalog(), input$asset_center_asset)$display_name,
        scope$provider_symbol, scope$provider_currency, result))
      # Bei Fremdwaehrung gehoert der Wechselkurs dazu: Ohne ihn ist der native
      # Kurs kein Snapshot in EUR.
      if (!identical(scope$provider_currency, "EUR")) {
        fx_symbol <- paste0(scope$provider_currency, "EUR=X")
        candidate <- list(symbol = fx_symbol, display_name = paste0(scope$provider_currency, "/EUR"),
          exchange = "CCY", quote_type = "currency", quote_currency = "EUR")
        # Ein fehlgeschlagener Wechselkursabruf darf den ganzen Snapshot nicht
        # blockieren: Der native Kurs bleibt gueltig, die Zeile nennt den Grund
        # (Festlegung 22.09.2026).
        fx_result <- tryCatch({
          fx_preview <- asset_center_fx_probe_service$preview(candidate, scope$provider_currency, "EUR",
            "direct", window_start, window_end, now_utc())
          asset_center_fx_probe_service$execute(fx_preview, TRUE)
        }, error = function(error) structure(list(code = spotcore::desktop_product_safe_error_code_v1(error)), class = "failed_quote"))
        rows[[length(rows) + 1L]] <- if (inherits(fx_result, "failed_quote"))
          list(quelle = paste0("Wechselkurs ", scope$provider_currency, "/EUR"), symbol = fx_symbol, waehrung = "EUR",
            wert = "—", stand = "—", art = paste0("Abruf fehlgeschlagen · ", fx_result$code))
          else asset_center_quote_row(paste0("Wechselkurs ", scope$provider_currency, "/EUR"), fx_symbol, "EUR", fx_result)
      }
      # Der Snapshot ist erst in EUR ein Snapshot: Die Umrechnung steht als eigene,
      # abgeleitete Zeile darunter, mit den beiden Staenden, aus denen sie stammt.
      if (length(rows) == 2L) {
        native <- suppressWarnings(as.numeric(rows[[1L]]$wert)); rate <- suppressWarnings(as.numeric(rows[[2L]]$wert))
        if (is.na(rate)) native <- NA_real_
        if (!is.na(native) && !is.na(rate))
          rows[[3L]] <- list(quelle = paste0(if (is.null(rows[[1L]]$basis)) rows[[1L]]$quelle else rows[[1L]]$basis, " in EUR"),
            symbol = "—", waehrung = "EUR",
            wert = format(native * rate, nsmall = 4L, scientific = FALSE),
            stand = paste0(rows[[1L]]$stand, " / ", rows[[2L]]$stand),
            art = "abgeleitet aus Kurs und Wechselkurs")
      }
      list(rows = rows, currency = scope$provider_currency, fetched_at = now_utc(),
           listed_since = if (is.character(result$first_trade_date) &&
             length(result$first_trade_date) == 1L) result$first_trade_date else NA_character_)
    }, function(value) {
      asset_center_snapshot_probe(value)
      state(list(tone = "neutral", title = "Tagesfrische Kurse abgerufen",
        copy = paste0(length(value$rows), " Quelle(n) gelesen · nichts in die Kurshistorie geschrieben. ",
          "Ein Zwischenstand der laufenden Sitzung ist kein Tagesschluss und wird nur angezeigt.",
          # Die Quelle nennt die Erstnotiz bei jedem Abruf mit. Sie hier zu zeigen
          # kostet nichts und beantwortet die Frage, ab wann ein Titel ueberhaupt
          # abrufbar ist (Festlegung 25.09.2026, #283).
          if (!is.na(value$listed_since))
            paste0(" Erstnotiz laut Quelle: ", format(as.Date(value$listed_since), "%d.%m.%Y"), ".") else "")))
    })
  })
  output$asset_center_snapshot_quote_table <- shiny::renderTable({
    value <- asset_center_snapshot_probe(); if (is.null(value)) return(data.frame())
    do.call(rbind, lapply(value$rows, function(row) data.frame(
      Quelle = row$quelle, Symbol = row$symbol, Währung = row$waehrung,
      Kurs = row$wert, Stand = row$stand, Art = row$art, check.names = FALSE)))
  }, striped = TRUE, bordered = FALSE)
  # Eigene Kursangaben: eintragen, lesen, in der Bewertung fortschreiben. Der
  # Eintrag ist eine Eigentuemerangabe, kein Marktkurs (#283 Punkt 2).
  asset_center_manual_price_read <- function() {
    asset_id <- desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", input$asset_center_asset)
    asset_center_manual_prices(asset_center_manual_price_service$read(asset_id))
  }
  action_feedback$observe('refresh', input$asset_center_manual_price_read, safe(asset_center_manual_price_read(), function(value)
    state(list(tone = "neutral", title = "Kursangaben gelesen",
      copy = paste(value$entry_count, "eigene Kursangaben für dieses Asset · nichts abgerufen, nichts geschrieben.")))))
  action_feedback$observe('refresh', input$asset_center_manual_price_save, {
    safe({
      selected <- asset_center_selected()
      if (!asset_center_manual_allowed(selected))
        stop("asset_center_market_method_invalid", call. = FALSE)
      asset_id <- desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", input$asset_center_asset)
      recorded <- asset_center_manual_price_service$append(asset_id, as.character(input$asset_center_manual_price_date),
        trimws(as.character(input$asset_center_manual_price_value)), selected$price_currency, now_utc(),
        isTRUE(input$asset_center_manual_price_confirm))
      list(recorded = recorded, entries = asset_center_manual_price_service$read(asset_id))
    }, function(value) {
      asset_center_manual_prices(value$entries)
      shiny::updateCheckboxInput(session, "asset_center_manual_price_confirm", value = FALSE)
      state(list(tone = "positive", title = "Kursangabe gespeichert",
        copy = paste0(format(as.Date(value$recorded$price_date), "%d.%m.%Y"), ": ", value$recorded$value_decimal, " ",
          value$recorded$currency, " · insgesamt ", value$entries$entry_count,
          " Angaben. Die Bewertung schreibt sie bis zur nächsten Angabe fort und kennzeichnet die Tage als Ersatzwerte.")))
    })
  })
  output$asset_center_manual_price_table <- shiny::renderTable({
    value <- asset_center_manual_prices(); if (is.null(value) || !length(value$entries)) return(data.frame())
    do.call(rbind, lapply(value$entries, function(row) data.frame(
      Tag = format(as.Date(row$price_date), "%d.%m.%Y"), Kurs = row$value_decimal,
      Währung = row$currency, Eingetragen = row$recorded_at_utc, check.names = FALSE)))
  }, striped = TRUE, bordered = FALSE)
  action_feedback$observe('refresh', input$asset_center_refresh_discard, {
    asset_center_refresh_pending(NULL)
    state(list(tone = "neutral", title = "Ansicht geschlossen",
      copy = "Es wurde keine Bewertung geschrieben. Abgerufene Kurse und Wechselkurse bleiben erhalten."))
  })
  shiny::observeEvent(input$asset_center_history_plan, {
    promotion <- asset_center_recover_history_promotion()
    if (is.null(promotion) || is.null(promotion$promotion_handle)) {
      state(list(tone = "error", title = "Historienplanung blockiert", copy = "Die gespeicherte Bindung an die Notierung konnte für die ausgewählte Zuordnung nicht geladen werden. Bitte Zuordnung prüfen; kein Kursabruf.")); return()
    }
    safe({
      private <- asset_center_provider_promotion_service$resolve_promotion(promotion$promotion_handle)
      asset_center_market_plan_service$plan(
        private$listing_ref, as.character(input$asset_center_history_start),
        as.character(input$asset_center_history_end), input$asset_center_history_mode
      )
    }, function(plan) {
      asset_center_market_plan(plan)
      asset_center_market_fetch_preview(NULL); asset_center_market_fetch_result(NULL)
      asset_center_market_review(NULL); asset_center_market_publication_result(NULL)
      choices <- data_asset_center_history_range_choices_v1(plan)
      shiny::updateSelectInput(session, "asset_center_history_range", choices = choices, selected = unname(choices[[1L]]))
      for (id in c("asset_center_history_fetch_confirm", "asset_center_history_publish_confirm", "asset_center_history_reject_confirm")) {
        shiny::updateCheckboxInput(session, id, value = FALSE)
      }
      state(list(
        tone = if (plan$target_day_count > 0L) "warning" else "positive",
        title = paste(plan$target_day_count, "Zieltage in", plan$range_count, "Zeiträumen"),
        copy = if(plan$target_day_count==0L) 'Für diesen Plan ist kein Abruf nötig. Gespeicherte Quelllücken sind keine fehlenden Datensätze; sie bleiben separat zu prüfen.' else 'Die Planung war nur lesend. Genau einen Bereich auswählen; Abruf und Veröffentlichung benötigen getrennte Bestätigungen.'
      ))
    })
  })
  shiny::observeEvent(input$asset_center_history_fetch_prepare, {
    promotion <- asset_center_recover_history_promotion()
    plan <- asset_center_market_plan()
    if (is.null(promotion) || is.null(promotion$promotion_handle) || is.null(plan)) {
      state(list(tone = 'warning', title = 'Zuerst Zeitraum planen', copy = 'Die sitzungslokale Planung fehlt, etwa nach einem Neustart. „Zeiträume nur lesend planen“ anklicken; kein Abruf wurde gestartet.')); return()
    }
    if(plan$target_day_count==0L) {
      state(list(tone='positive',title='Kein Abruf erforderlich',copy='Dieser Plan enthält keine Abrufbereiche. Quelllücken bleiben separat sichtbar.'));return()
    }
    safe({
      if (!identical(plan$mode, input$asset_center_history_mode) ||
          !identical(plan$required_start_date, as.character(input$asset_center_history_start)) ||
          !identical(plan$as_of_date, as.character(input$asset_center_history_end))) {
        stop('Zeitraum oder Modus geändert: bitte „Zeiträume nur lesend planen“ erneut ausführen. Kein Abruf gestartet.',call.=FALSE)
      }
      selected_range <- data_asset_center_selected_history_range_v1(plan, input$asset_center_history_range)
      private <- asset_center_provider_promotion_service$resolve_promotion(promotion$promotion_handle)
      invisible(data_provider_mapping_editor_refresh_v1(asset_center_provider_editor, runtime$context))
      mapping <- data_provider_mapping_editor_resolve_history_scope_v1(asset_center_provider_editor, runtime$context, input$asset_center_mapping)
      promotion_binding <- list(
        listing_ref = private$listing_ref,
        listing_fingerprint = private$listing_fingerprint,
        mapping_id = private$mapping_id,
        mapping_revision = as.integer(private$mapping_revision),
        mapping_fingerprint = private$mapping_fingerprint
      )
      asset_center_market_review_service$preview(
        private$listing_ref, mapping, promotion_binding, selected_range$start_date,
        selected_range$end_date, plan$mode, now_utc()
      )
    }, function(preview) {
      asset_center_market_fetch_preview(preview); asset_center_market_fetch_result(NULL)
      asset_center_market_review(NULL); asset_center_market_publication_result(NULL)
      shiny::updateCheckboxInput(session, "asset_center_history_fetch_confirm", value = FALSE)
      state(list(
        tone = "warning",
        title = paste(preview$target_day_count, "Kalendertage für genau einen Abruf vorbereitet"),
        copy = "Noch gab es weder Netzwerkzugriff noch ein Schreiben von Marktdaten. Die erste Bestätigung erlaubt nur den Abruf und das Vormerken lokal beim Eigentümer."
      ))
    })
  })
  shiny::observeEvent(input$asset_center_history_fetch_execute, {
    preview <- asset_center_market_fetch_preview()
    if (is.null(preview)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("data_market_history_review_preview_required"))); return()
    }
    safe({ asset_center_require_market(TRUE); asset_center_market_review_service$stage(preview, isTRUE(input$asset_center_history_fetch_confirm)) }, function(review) {
      asset_center_market_review(review)
      asset_center_market_fetch_result(list(status = "staged_review", review = review))
      asset_center_market_fetch_preview(NULL); asset_center_market_publication_result(NULL)
      shiny::updateCheckboxInput(session, "asset_center_history_fetch_confirm", value = FALSE)
      shiny::updateCheckboxInput(session, "asset_center_history_publish_confirm", value = FALSE)
      shiny::updateCheckboxInput(session, "asset_center_history_reject_confirm", value = FALSE)
      state(list(
        tone = "warning", title = "Kurskandidat lokal beim Eigentümer vorgemerkt",
        copy = "Tabelle und Plot zeigen den unveröffentlichten Kandidaten. Für die Veröffentlichung ist eine neue exakte Bestätigung erforderlich; dabei erfolgt kein neuer Abruf."
      ))
    })
  })
  shiny::observeEvent(input$asset_center_history_recover, {
    promotion <- asset_center_provider_promotion_result()
    if (is.null(promotion) || is.null(promotion$promotion_handle)) {
      state(list(tone = "error", title = "Abgleich blockiert", copy = pl_error_text_v1("data_market_history_review_service_invalid"))); return()
    }
    safe({
      private <- asset_center_provider_promotion_service$resolve_promotion(promotion$promotion_handle)
      asset_center_market_review_service$recover(private$listing_ref)
    }, function(recovered) {
      if (is.null(recovered)) {
        state(list(tone = "neutral", title = "Kein vorgemerkter Prüfvorgang", copy = "Für diese Notierung liegt kein Kandidat lokal beim Eigentümer vor.")); return()
      }
      asset_center_market_review(recovered$public_review)
      asset_center_market_fetch_result(list(
        status = recovered$state, review = recovered$public_review,
        recovery_result = if (recovered$state %in% c("fetch_failed", "recovery_required")) recovered$public_result else NULL
      ))
      asset_center_market_publication_result(
        if (recovered$state %in% c("published", "rejected")) recovered$public_result else NULL
      )
      for (id in c("asset_center_history_fetch_confirm", "asset_center_history_publish_confirm", "asset_center_history_reject_confirm")) {
        shiny::updateCheckboxInput(session, id, value = FALSE)
      }
      state(list(
        tone = if (identical(recovered$state, "published")) "positive" else if (recovered$state %in% c("rejected", "fetch_failed")) "neutral" else "warning",
        title = paste("Prüfvorgang abgeglichen ·", recovered$state),
        copy = if (identical(recovered$state, "recovery_required")) {
          "Der Effekt bleibt mehrdeutig. Abruf, Veröffentlichung und Verwerfen bleiben blockiert; es erfolgt kein automatischer neuer Versuch."
        } else {
          "Der gespeicherte Zustand wurde exakt abgeglichen; es erfolgte weder ein Kursabruf noch ein automatischer neuer Schreibversuch."
        }
      ))
    })
  })
  shiny::observeEvent(input$asset_center_history_publish, {
    review <- asset_center_market_review()
    if (is.null(review)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("data_market_history_review_preview_required"))); return()
    }
    safe({ asset_center_require_market(TRUE); asset_center_market_review_service$publish(review, isTRUE(input$asset_center_history_publish_confirm), now_utc()) }, function(result) {
      asset_center_market_publication_result(result)
      asset_center_market_fetch_result(list(status = "published", review = review))
      shiny::updateCheckboxInput(session, "asset_center_history_publish_confirm", value = FALSE)
      asset_center_history_state(if (result$source_gap_count > 0L) "source_gap" else "partial")
      promotion <- asset_center_provider_promotion_result()
      if (!is.null(promotion) && !is.null(promotion$promotion_handle)) {
        private <- asset_center_provider_promotion_service$resolve_promotion(promotion$promotion_handle)
        refreshed <- tryCatch(asset_center_market_plan_service$plan(
          private$listing_ref, as.character(input$asset_center_history_start),
          as.character(input$asset_center_history_end), "incremental"
        ), error = function(error) NULL)
        if (!is.null(refreshed)) {
          asset_center_market_plan(refreshed)
          choices <- data_asset_center_history_range_choices_v1(refreshed)
          shiny::updateSelectInput(session, "asset_center_history_range", choices = choices, selected = unname(choices[[1L]]))
        }
      }
      state(list(
        tone = if (result$source_gap_count > 0L) "warning" else "positive",
        title = "Exakt geprüfter Kurskandidat veröffentlicht",
        copy = paste(result$appended_day_count, "neu ·", result$corrected_day_count, "korrigiert ·", result$unchanged_day_count, "unverändert · kein erneuter Abruf beim Kursanbieter.")
      ))
    })
  })
  shiny::observeEvent(input$asset_center_history_reject, {
    review <- asset_center_market_review()
    if (is.null(review)) {
      state(list(tone = "error", title = "Aktion blockiert", copy = pl_error_text_v1("data_market_history_review_preview_required"))); return()
    }
    safe({ asset_center_require_market(TRUE); asset_center_market_review_service$reject(review, isTRUE(input$asset_center_history_reject_confirm), now_utc()) }, function(result) {
      asset_center_market_publication_result(result)
      asset_center_market_fetch_result(list(status = "rejected", review = review))
      shiny::updateCheckboxInput(session, "asset_center_history_reject_confirm", value = FALSE)
      state(list(
        tone = "neutral", title = "Kurskandidat verworfen",
        copy = "Der gespeicherte Kandidat wurde endgültig verworfen; es gab weder ein Schreiben von Marktdaten noch einen Kursabruf."
      ))
    })
  })
  shiny::observeEvent(input$activity_scope_assets, {
    selected <- input$activity_scope_assets
    if (is.null(selected)) selected <- character()
    activity_scope_selected(as.character(selected))
  }, ignoreInit = TRUE, ignoreNULL = FALSE)
  shiny::observeEvent(input$activity_scope_excluded_assets, {
    selected <- input$activity_scope_excluded_assets
    if (is.null(selected)) selected <- character()
    activity_scope_excluded(as.character(selected))
  }, ignoreInit = TRUE, ignoreNULL = FALSE)
  shiny::observeEvent(input$activity_scope_accounts, {
    selected <- input$activity_scope_accounts
    if (is.null(selected)) selected <- character()
    activity_scope_accounts(as.character(selected))
  }, ignoreInit = TRUE, ignoreNULL = FALSE)
  shiny::observeEvent(input$activity_scope_mode, {
    activity_scope_view_mode(as.character(input$activity_scope_mode))
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$activity_scope_domain, {
    selected <- input$activity_scope_domain
    if (is.null(selected)) selected <- character()
    activity_scope_domains(as.character(selected))
  }, ignoreInit = TRUE, ignoreNULL = FALSE)
  shiny::observeEvent(input$activity_scope_account_match, {
    activity_scope_account_match(as.character(input$activity_scope_account_match))
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$activity_scope_account_usage, {
    activity_scope_account_usage(as.character(input$activity_scope_account_usage))
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$activity_scope_interval_enabled, {
    activity_scope_interval_enabled(isTRUE(input$activity_scope_interval_enabled))
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$activity_scope_interval_from, {
    value <- input$activity_scope_interval_from
    activity_scope_interval_from(if (is.null(value) || length(value) != 1L || is.na(value)) NULL else as.character(value))
  }, ignoreInit = TRUE, ignoreNULL = FALSE)
  shiny::observeEvent(input$activity_scope_interval_to, {
    value <- input$activity_scope_interval_to
    activity_scope_interval_to(if (is.null(value) || length(value) != 1L || is.na(value)) NULL else as.character(value))
  }, ignoreInit = TRUE, ignoreNULL = FALSE)
  shiny::observeEvent(input$activity_scope_interval_relation, {
    activity_scope_interval_relation(as.character(input$activity_scope_interval_relation))
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$activity_scope_holding_mode, {
    activity_scope_holding_mode(as.character(input$activity_scope_holding_mode))
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$activity_scope_reset, {
    reset_activity_scope_controls()
  }, ignoreInit = TRUE)

  shiny::observeEvent(input$asset_center_activity_handoff, safe(refresh_activity_catalog(), function(model) {
    view <- tryCatch(sync_activity_workflow(),error=function(error)list(dirty=any(!vapply(
      list(input$activity_type,input$activity_asset,input$activity_account,input$activity_quantity,input$activity_gross),is.null,logical(1L)))))
    if (isTRUE(view$dirty) || length(view$selected_refs) || length(workflow_refs())) {
      state(list(tone='warning',title='Transaktionsentwurf bleibt erhalten',copy='Zuerst in der Buchungsauswahl bewusst zur Neuanlage wechseln und vorhandene Eingaben bei Bedarf ausdrücklich verwerfen.'))
      return(invisible(NULL))
    }
    shiny::updateTabsetPanel(session, "asset_center_step", selected = "transactions")
    selected_ref <- tryCatch({
      internal_asset <- desktop_catalog_editor_internal_identity_v1(
        asset_center_catalog_editor, runtime$context, "asset", input$asset_center_asset
      )
      data_asset_activity_editor_ref_for_internal_v1(
        activity_editor, runtime$context, "asset", internal_asset
      )
    }, error = function(error) NULL)
    available <- is.character(selected_ref) && length(selected_ref) == 1L && nzchar(selected_ref)
    if (available) {
      activity_scope_selected(selected_ref)
      activity_scope_excluded(character())
      activity_scope_accounts(character())
      activity_scope_view_mode("manual")
      activity_scope_domains("noncash")
      activity_scope_account_match("any")
      activity_scope_account_usage("current")
      activity_scope_interval_enabled(FALSE)
      activity_scope_interval_from(NULL)
      activity_scope_interval_to(NULL)
      activity_scope_interval_relation("activity")
      activity_scope_holding_mode("any_time")
      shiny::updateSelectizeInput(
        session, "activity_scope_assets", choices = multi_choice_vector(model$assets),
        selected = selected_ref, server = TRUE
      )
      shiny::updateSelectizeInput(
        session, "activity_scope_excluded_assets", choices = multi_choice_vector(model$assets),
        selected = character(), server = TRUE
      )
      shiny::updateSelectizeInput(
        session, "activity_scope_accounts", choices = multi_choice_vector(model$accounts),
        selected = character(), server = TRUE
      )
      # Nur die Auswahl setzen: Die Optionsliste hat refresh_activity_catalog()
      # unmittelbar zuvor gesetzt. Sie hier erneut zu schreiben verwirft die
      # abhaengigen Konto-/Zielauswahlen.
      activity_asset_update(selected = selected_ref)
      shiny::updateRadioButtons(session, "activity_scope_mode", selected = "manual")
      shiny::updateCheckboxGroupInput(session, "activity_scope_domain", selected = "noncash")
      shiny::updateRadioButtons(session, "activity_scope_account_match", selected = "any")
      shiny::updateRadioButtons(session, "activity_scope_account_usage", selected = "current")
      shiny::updateCheckboxInput(session, "activity_scope_interval_enabled", value = FALSE)
      session$sendInputMessage("activity_scope_interval_from", list(value = ""))
      session$sendInputMessage("activity_scope_interval_to", list(value = ""))
      shiny::updateRadioButtons(session, "activity_scope_interval_relation", selected = "activity")
      shiny::updateRadioButtons(session, "activity_scope_holding_mode", selected = "any_time")
      activity_asset_update(selected = selected_ref)
    }
    selected_activity_account <- tryCatch({
      if (is.null(input$asset_center_custody_account) || !nzchar(input$asset_center_custody_account)) {
        NULL
      } else {
        internal_account <- desktop_catalog_editor_internal_identity_v1(
          asset_center_catalog_editor, runtime$context, "account", input$asset_center_custody_account
        )
        ref <- data_asset_activity_editor_ref_for_internal_v1(
          activity_editor, runtime$context, "account", internal_account
        )
        rows <- Filter(function(row) identical(row$ref, ref), model$accounts)
        if (length(rows) == 1L) rows[[1L]] else NULL
      }
    }, error = function(error) NULL)
    if (!is.null(selected_activity_account)) {
      shiny::updateSelectInput(session, "activity_portfolio", selected = selected_activity_account$portfolio_ref)
      shiny::updateSelectInput(session, "activity_account", selected = selected_activity_account$ref)
    }
    asset_center_activity_state(if (available) "available" else "not_checked")
    state(list(
      tone = if (available) "positive" else "warning",
      title = if (available) "Buchungsmaske sichtbar geöffnet" else "Übergabe an die Buchungsmaske nicht möglich",
      copy = if (available) {
        "Der Bereich Transaktionen manuell erfassen wurde geöffnet; Assetfilter und genau ein Transaktionsziel sind vorausgewählt. Ein optional gewähltes Konto / Wallet wurde übernommen."
      } else {
        pl_error_text_v1("data_asset_center_selection_invalid")
      }
    ))
  }))

  shiny::observeEvent(input$activity_refresh, safe(refresh_activity_catalog(), function(value) {
    refresh_activity_event_choices()
    refresh_activity_account_choices()
    state(list(tone="neutral", title="Buchungsauswahl bereit", copy="Nur browserlokale Auswahlverweise wurden veröffentlicht; noch kein Schreiben."))
  }))
  # Buchungsart folgt dem gewaehlten Asset (#449, Festlegung 16.10.2026): EUR-Cash -> Cash, Devisen -> Devisen, sonst Non-Cash.
  # Nur bei einem Wechsel melden, damit Auswahl und Buchungsart sich nicht gegenseitig anstossen.
  # Verglichen wird auch mit dem zuletzt gesendeten Wert (#511): Wechselt die Suche kurz hintereinander, steht in
  # input$transactions_mode noch der Stand vor der ersten Umstellung - deren Echo ist unterwegs. Ohne den Vergleich blieb die
  # zweite Umstellung aus, und der Browser behielt die erste (etwa EUR-Cash gewaehlt, Buchungsart Non-Cash).
  transactions_mode_sent <- NULL
  transactions_mode_follow <- function(asset_type) {
    mode <- desktop_transactions_mode_v1(asset_type)
    if (is.null(mode) || (identical(mode, input$transactions_mode) && identical(mode, transactions_mode_sent))) return(invisible(NULL))
    transactions_mode_sent <<- mode
    shiny::updateRadioButtons(session, "transactions_mode", selected = mode)
  }
  # Seit rc.332 waehlt der Start kein Asset vor; eine Buchungsart folgt nur einer Wahl in der Suche. (Bis rc.331 durfte die
  # automatische Vorauswahl keine waehlen - war das erste Asset eine Devise, blendete der Start die Belegimporte aus.)
  shiny::observeEvent(input$asset_center_asset, {
    asset <- asset_center_selected(); if (!is.null(asset)) transactions_mode_follow(asset$asset_type)
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$asset_center_asset_clear, shiny::updateSelectizeInput(session, "asset_center_asset", selected = ""), ignoreInit = TRUE)
  # Die Maske uebernimmt das Asset der Suche; dann hat der Beobachter oben schon entschieden. Hier zaehlt nur eine eigene Wahl im Formular.
  shiny::observeEvent(input$activity_asset, {
    if (activity_asset_server_echo(input$activity_asset)) return()
    model <- activity_catalog(); if (is.null(model)) return()
    if (identical(input$activity_asset, activity_ref_for_center("asset", input$asset_center_asset))) return()
    hit <- Filter(function(value) identical(value$ref, input$activity_asset), model$assets)
    if (length(hit) == 1L) transactions_mode_follow(hit[[1L]]$asset_type)
  }, ignoreInit = TRUE)
  # Devisen buchen mit denselben Typen; die Maske nennt sie fachlich. Ein Zugang bei Devisen ist meist ein Zufluss aus
  # Ertrag: Kontext "Sonstiges" (der Kern verlangt bei Zugaengen einen Kontext).
  shiny::observeEvent(input$transactions_mode, {
    mode <- if (identical(input$transactions_mode, "fx")) "fx" else "non_cash"
    choices <- desktop_activity_type_choices_v1(mode)
    selected <- if (isTRUE(input$activity_type %in% choices)) input$activity_type else "buy"
    shiny::updateSelectInput(session, "activity_type", choices = choices, selected = selected)
  }, ignoreInit = TRUE)
  shiny::observeEvent(list(input$activity_type, input$transactions_mode), {
    if (identical(input$transactions_mode, "fx") && identical(input$activity_type, "deposit") &&
        isTRUE(input$activity_movement_context %in% c("not_applicable", "unclassified")))
      shiny::updateSelectInput(session, "activity_movement_context", selected = "other")
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$activity_type, {
    refresh_activity_event_choices()
    if(!identical(input$activity_type,"stock_dividend"))shiny::updateSelectInput(session,"activity_source_asset",selected="")
    if(!desktop_product_activity_field_applies_v1(input$activity_type,"eligible_quantity"))shiny::updateTextInput(session,"activity_eligible_quantity",value="")
    if(!desktop_product_activity_field_applies_v1(input$activity_type,"monetary_fee"))shiny::updateTextInput(session,"activity_monetary_fee",value="")
    if(!"asset_fee"%in%desktop_product_activity_relevant_fields_v1(input$activity_type))shiny::updateTextInput(session,"activity_asset_fee",value="")
    if(input$activity_type%in%c("withdrawal","transfer")){
      shiny::updateTextInput(session,"activity_unit_price",value="");shiny::updateTextInput(session,"activity_gross_total",value="")
    }
    shiny::updateSelectInput(session,"activity_movement_context",selected="not_applicable")
    shiny::updateSelectInput(session,"activity_acquisition_evidence",selected="not_applicable")
  }, ignoreInit=TRUE)
  shiny::observeEvent(list(input$activity_portfolio, input$activity_asset, input$activity_type), refresh_activity_account_choices(), ignoreInit=TRUE)
  shiny::observeEvent(list(input$activity_quick_portfolio,input$activity_quick_asset),{
    model<-activity_catalog();if(is.null(model))return(invisible(NULL));choices<-.data_asset_activity_account_choice_state_v1(model,input$activity_quick_portfolio,input$activity_quick_asset,input$activity_quick_default_account,"");selected<-if(nzchar(choices$account_ref))choices$account_ref else if(length(choices$accounts))choices$accounts[[1L]]$ref else "";shiny::updateSelectInput(session,"activity_quick_default_account",choices=choice_vector(choices$accounts),selected=selected)
  },ignoreInit=TRUE)
  shiny::observeEvent(list(
    input$activity_type, input$activity_portfolio, input$activity_account, input$activity_related_account,
    input$activity_asset, input$activity_source_asset, input$activity_time_evidence, input$activity_date,
    input$activity_time, input$activity_zone, input$activity_utc, input$activity_amount_mode,
    input$activity_basis_mode, input$activity_quantity, input$activity_eligible_quantity,
    input$activity_unit_price, input$activity_gross_total, input$activity_monetary_fee,
    input$activity_net_total, input$activity_net_unit_price, input$activity_net_tax_rate,
    input$activity_asset_fee, input$activity_provided_basis, input$activity_movement_context,
    input$activity_acquisition_evidence, input$activity_acquisition_date, input$activity_acquisition_time,
    input$activity_acquisition_zone, input$activity_acquisition_utc
  ), {
    tryCatch(sync_activity_workflow(),error=function(error)NULL)
    done <- activity_completed()
    if(is.null(done) || !identical(activity_form(), done$form)) {
      activity_completed(NULL); action_feedback$clear('activity')
    }
    action_feedback$clear('correction')
    if(!is.null(correction_preview())) {
      correction_preview(NULL); shiny::updateCheckboxInput(session,'activity_correction_confirm',value=FALSE)
    }
    if (!is.null(activity_preview()) || !is.null(scale_preview())) {
      activity_preview(NULL); scale_preview(NULL); activity_approval(NULL)
      shiny::updateCheckboxInput(session, "activity_scale_confirm", value=FALSE)
      state(list(tone="warning", title="Buchungsvorschau verworfen", copy="Formularwerte wurden geändert. Eine neue Mengen-/FIFO-Vorschau ist erforderlich."))
    }
  }, ignoreInit=TRUE)
  # Transaktions-ID und Adresse der Neuanlage (#439): vor dem Pruefen und vor dem Speichern gleich geprueft, damit eine
  # gespeicherte Buchung nicht an einer abgewiesenen Kennung haengt.
  activity_reference_entry <- function() {
    id <- data_activity_reference_text_v1(input$activity_transaction_id)
    address <- if (isTRUE(activity_asset_is_crypto())) data_activity_reference_text_v1(input$activity_counterparty_address) else NULL
    list(transaction_id = id, counterparty_address = address,
      valid = data_activity_reference_token_valid_v1(id) && data_activity_reference_token_valid_v1(address))
  }
  activity_reference_entry_complaint <- "Transaktions-ID und Adresse sind je eine zusammenhängende Zeichenfolge ohne Leerzeichen (höchstens 200 Zeichen). Freitext gehört in die Notiz im Bereich „Beleg“ der Buchung."
  action_feedback$observe("activity", input$activity_prepare, {
    allowed <- tryCatch({require_activity_workflow("create");TRUE},error=function(error)FALSE)
    if (!allowed) {state(list(tone="warning",title="Neuanlage gesperrt",copy="Zuerst die Buchungsauswahl bewusst übernehmen. Eine ausgewählte Buchung wird nicht als Neuanlage gespeichert."));return()}
    activity_completed(NULL); action_feedback$clear('activity')
    if (!isTRUE(activity_reference_entry()$valid)) {state(list(tone="warning",title="Transaktions-ID unzulässig",copy=activity_reference_entry_complaint));return()}
    form <- activity_form()
    # Vor dem Vertrag im Klartext pruefen, was dort nur einen Sammelcode ergibt.
    klage<-activity_amount_complaint(form)
    if(!is.null(klage)){
      state(list(tone="warning",title="Betrag unzulässig",copy=klage));return()
    }
    pflicht<-activity_required_complaint(form)
    if(!is.null(pflicht)){
      state(list(tone="warning",title="Angabe fehlt",copy=pflicht));return()
    }
    if(identical(form$event_type,"transfer")){
      issues<-activity_form_issues(form)
      if(length(issues)){
        state(list(tone="warning",title="Transfer-Eingaben ergänzen",copy=paste("Bitte prüfen:",paste(issues,collapse=" · "))))
        return()
      }
    }
    safe({
      scale <- data_asset_quantity_scale_prepare_for_activity_v1(
        scale_center, activity_editor, runtime$context, form, now_utc()
      )
      if (identical(scale$status, "ready_for_confirmation")) {
        list(kind="scale", value=scale)
      } else {
        list(kind="activity", value=data_asset_activity_editor_prepare_v1(
          activity_editor, runtime$context, form, now_utc()
        ))
      }
    }, function(prepared) {
      activity_approval(NULL)
      shiny::updateCheckboxInput(session, "activity_scale_confirm", value=FALSE)
      if (identical(prepared$kind, "scale")) {
        activity_preview(NULL); scale_preview(prepared$value)
        state(list(
          tone="warning", title="Feinere Mengenskala erforderlich",
          copy=prepared$value$warning_text
        ))
      } else {
        scale_preview(NULL); activity_preview(prepared$value)
        preview <- prepared$value
        activity_approval(preview$preview_ref)
        state(list(tone="warning", title="Buchungsvorschau bereit", copy=paste0("Wirkung: ", pl_label_v1(DESKTOP_ACTIVITY_FIFO_EFFECT_LABELS_V1, preview$fifo_effect_code),
          " · Ø Einstandskurs: ", if (is.null(preview$cost_average_decimal)) pl_label_v1(DESKTOP_ACTIVITY_COST_AVERAGE_LABELS_V1, preview$cost_average_status)
          else activity_price(preview$cost_average_decimal, ""), " · keine Cash-Buchung · Mit \u201eSpeichern\u201c wird genau diese Vorschau gebucht.")))
      }
    })
  })
  action_feedback$observe("activity", input$activity_execute, {
    allowed <- tryCatch({require_activity_workflow("create");TRUE},error=function(error)FALSE)
    if (!allowed) {state(list(tone="warning",title="Neuanlage gesperrt",copy="Aktive Buchungsauswahl oder ausstehender Auswahlwechsel. Keine neue Buchung gespeichert."));return()}
    preview <- activity_preview()
    submitted_form <- activity_form()
    if (is.null(preview) || !identical(activity_approval(),preview$preview_ref)) {
      state(list(tone="error", title="Buchung blockiert", copy=pl_error_text_v1("data_asset_activity_editor_confirmation_required"))); return()
    }
    kennung <- activity_reference_entry()
    if (!isTRUE(kennung$valid)) {state(list(tone="warning",title="Transaktions-ID unzulässig",copy=activity_reference_entry_complaint));return()}
    activity_approval(NULL)
    safe({
      data_asset_activity_editor_confirm_v1(activity_editor, runtime$context, preview$preview_ref)
      data_asset_activity_editor_execute_v1(activity_editor, runtime$context, preview$preview_ref, now_utc())
    }, function(result) {
      activity_preview(NULL); activity_approval(NULL)
      if (isTRUE(result$canonical_write)) {
        activity_last_successful_context(list(
          portfolio_ref=submitted_form$portfolio_ref,
          account_ref=submitted_form$account_ref,
          asset_ref=submitted_form$asset_ref,
          local_date=submitted_form$local_date
        ))
      }
      invisible(read_workspace()); invisible(refresh_activity_catalog()); invisible(refresh_activity_corrections())
      # Eine Buchung vor einem erklaerten Pflegestand setzt diesen zurueck; der
      # Hinweis muss das sofort zeigen (#423).
      asset_maintenance_refresh()
      last_context <- activity_last_successful_context()
      if (is.list(last_context) && inherits(last_context$local_date,"Date") && length(last_context$local_date)==1L && !is.na(last_context$local_date)) {
        shiny::updateDateInput(session,"activity_date",value=last_context$local_date)
      }
      materialized<-update_realized_state("incremental")
      position <- if (is.null(materialized)) NULL else activity_position_after_write(submitted_form)
      activity_completed(list(form=submitted_form, fresh=!is.null(materialized), position=position))
      if (!is.null(activity_workflow)) {activity_workflow$mark_saved();activity_workflow_view(activity_workflow$view())}
      copy <- if (is.null(materialized)) {
        "Die Buchung ist gespeichert. Der abgeleitete FIFO-Bestand ist noch nicht aktuell; Berechnungsstand separat prüfen. Nicht erneut buchen."
      } else if (is.null(position)) {
        "Die Buchung ist gespeichert und der FIFO-Bestand aktualisiert. Der Bestand des Assets ist hier nicht eindeutig darstellbar; die Bestandskontrolle zeigt den Stand. Keine automatische Cash-Buchung und kein Portfolioabschluss."
      } else {
        paste0("Die Buchung ist gespeichert und der FIFO-Bestand aktualisiert. Stand des Assets jetzt: ", position, ". Keine automatische Cash-Buchung und kein Portfolioabschluss.")
      }
      # Belegangaben an die eben gespeicherte Buchung; scheitert das, bleibt die Buchung und die Meldung sagt es.
      if (!is.null(kennung$transaction_id) || !is.null(kennung$counterparty_address)) {
        eingetragen <- tryCatch({
          activity_reference_service$record(result$trusted_event_ref, kennung$transaction_id, kennung$counterparty_address, NULL, now_utc(), TRUE); TRUE
        }, error = function(error) FALSE)
        copy <- paste(copy, if (eingetragen) "Transaktions-ID und Adresse stehen an der Buchung." else
          "Transaktions-ID und Adresse ließen sich nicht eintragen – bitte im Bereich „Beleg“ der Buchung nachholen.")
        if (eingetragen) activity_reference_tick(activity_reference_tick() + 1L)
      }
      shiny::updateTextInput(session, "activity_transaction_id", value = ""); shiny::updateTextInput(session, "activity_counterparty_address", value = "")
      state(list(tone=if(is.null(materialized))"warning"else"positive", title="Transaktion gespeichert", copy=copy))
    })
  })
  action_feedback$observe("activity", input$activity_scale_execute, {
    preview <- scale_preview()
    if (is.null(preview) || !isTRUE(input$activity_scale_confirm)) {
      state(list(tone="error", title="Skalenanpassung blockiert", copy=pl_error_text_v1("data_asset_quantity_scale_confirmation_required"))); return()
    }
    safe({
      data_asset_quantity_scale_confirm_v1(scale_center, runtime$context, preview$preview_ref)
      data_asset_quantity_scale_execute_v1(scale_center, runtime$context, preview$preview_ref, now_utc())
    }, function(result) {
      scale_preview(NULL); shiny::updateCheckboxInput(session, "activity_scale_confirm", value=FALSE)
      invisible(refresh_activity_catalog()); materialized <- update_realized_state("incremental")
      state(list(
        tone=if(is.null(materialized))"warning"else"neutral",
        title="Mengenskala erhöht",
        copy=paste(
          "Skala", result$current_quantity_scale, "→", result$proposed_quantity_scale,
          "· keine Rundung · FIFO-Stand", if(is.null(materialized))"sichtbar stale"else"aktualisiert",
          "· Buchung jetzt erneut prüfen."
        )
      ))
    })
  })
  scale_resume_offer <- function(model) {
    scale_pending(model)
    choices <- if(!length(model$candidates)) c("Keine unterbrochenen Anpassungen"="") else c(
      "Bitte wählen"="", stats::setNames(
        vapply(model$candidates, `[[`, character(1L), "resume_ref"),
        vapply(model$candidates, function(item) paste(
          item$current_quantity_scale, "→", item$proposed_quantity_scale, "·", item$status
        ), character(1L))
      )
    )
    shiny::updateSelectInput(session, "activity_scale_resume_ref", choices=choices, selected="")
  }
  shiny::observeEvent(input$activity_scale_pending_refresh, safe(
    data_asset_quantity_scale_pending_v1(scale_center, runtime$context),
    function(model) {
      scale_resume_offer(model)
      state(list(tone=if(length(model$candidates))"warning"else"neutral", title="Unterbrochene Skalenanpassungen gelesen", copy=paste(length(model$candidates), "fortsetzbare Anpassungen.")))
    }
  ))
  shiny::observeEvent(input$activity_scale_resume, {
    ref <- input$activity_scale_resume_ref
    if(is.null(ref) || !nzchar(ref)) {
      state(list(tone="error", title="Wiederaufnahme der Skalenanpassung blockiert", copy=pl_error_text_v1("data_asset_quantity_scale_resume_invalid"))); return()
    }
    safe(data_asset_quantity_scale_resume_v1(scale_center, runtime$context, ref), function(result) {
      invisible(refresh_activity_catalog()); materialized <- update_realized_state("incremental")
      state(list(tone=if(is.null(materialized))"warning"else"neutral", title="Skalenanpassung fortgesetzt", copy=paste("Skala",result$current_quantity_scale,"→",result$proposed_quantity_scale,"· FIFO-Stand",if(is.null(materialized))"stale"else"aktualisiert")))
    })
  })
  shiny::observeEvent(list(input$activity_rows_selected,input$activity_correction_action,activity_sequence()), {
    correction_preview(NULL); action_feedback$clear('correction')
    shiny::updateCheckboxInput(session,'activity_selection_discard',value=FALSE)
    shiny::updateCheckboxInput(session,'activity_correction_confirm',value=FALSE)
    activity_preview(NULL);activity_approval(NULL)
    loading_current <- !is.null(activity_workflow_loading) && !is.null(activity_workflow) &&
      identical(workflow_refs(),activity_workflow$view()$selected_refs) && identical(input$activity_correction_action,'correct')
    if (!is.null(activity_workflow) && !loading_current) {activity_workflow$revoke();activity_workflow_view(activity_workflow$view())}
  },ignoreInit=TRUE,priority=100)
  shiny::observeEvent(input$activity_correction_action, {
    if (is.null(activity_workflow) || length(activity_workflow$view()$selected_refs)!=1L) return()
    if (input$activity_correction_action %in% c('correct','void')) {
      if (!identical(activity_workflow$view()$action,input$activity_correction_action)) {
        activity_workflow$set_action(input$activity_correction_action)
        activity_workflow_loading <<- NULL
      }
      activity_workflow_view(activity_workflow$view())
    }
  },ignoreInit=TRUE,priority=90)
  shiny::observeEvent(input$activity_quick_file, {
    activity_quick_inspection(NULL); activity_quick_prepared(NULL); activity_quick_loaded_profile(NULL)
    action_feedback$clear(c('import','profile'))
    shiny::updateCheckboxInput(session,'activity_quick_confirm',value=FALSE)
  },ignoreInit=TRUE,priority=100)
  # Das Haekchen wirkt sofort, sonst waere nicht erkennbar, dass es etwas tut.
  shiny::observeEvent(input$activity_correction_focus_asset,
    tryCatch(invisible(refresh_activity_corrections()),error=function(error)NULL),ignoreInit=TRUE)
  # Die Buchungsliste laedt von selbst, sobald der Reiter sie zeigt. Gelesen wird einmal je
  # Sitzung, danach
  # liest jeder Schreibvorgang selbst neu. Ohne ignoreInit: Der offene Reiter ist
  # Startzustand und kein Wechsel.
  shiny::observeEvent(input$asset_center_step, {
    if (identical(input$asset_center_step, "transactions") && is.null(correction_model()))
      tryCatch(invisible(refresh_activity_corrections()), error = function(error) invisible(NULL))
  })
  action_feedback$observe('correction', input$activity_correction_refresh,safe(refresh_activity_corrections(),function(value){state(list(tone="neutral",title="Korrekturauswahl bereit",copy="Aktive Vorgänger sind nur über flüchtige Auswahl-Refs gebunden."))}))
  # Die Tabellenauswahl uebernimmt den Vorgaenger selbst. Vorher war das ein
  # eigener Klick ("Auswahl uebernehmen"), und ohne ihn meldete jede Korrektur
  # activity_workflow_selection_pending - als blanker
  # Sammelcode desktop_product_boundary_failed (07.10.2026, #424). Der Schutz
  # gegen Datenverlust bleibt: liegen unbestaetigte Formulareingaben vor, verlangt
  # der Workflow weiter das ausdrueckliche Verwerfen.
  activity_apply_selection <- function(released = FALSE) {
      # Ein alter Durchgangsbericht darf nicht neben einer neuen Auswahl stehen.
      # Nicht im Aufraeumbeobachter: Der laeuft auch, wenn die Reihe gerade
      # ausgelaufen ist, und hat damit genau den Bericht geloescht, den der
      # letzte Schritt eben erzeugt hatte (#424).
      # Auch nicht bei der Freigabe nach dem letzten Schritt einer Reihe: Dort
      # ist die Auswahl leer, weil die Reihe fertig ist, nicht weil eine neue
      # Arbeit beginnt.
      if (is.null(activity_sequence()) && !isTRUE(released)) activity_sequence_report(NULL)
      # Das Verwerfen-Zeichen der Reihe gilt fuer den ganzen Durchlauf, auch fuer
      # das Laden des Vorgaengers.
      reihe_verwerfen <- isTRUE(activity_sequence_discard())
      on.exit(activity_sequence_discard(FALSE), add = TRUE)
      selected <- tryCatch({
        view <- sync_activity_workflow()
        refs <- workflow_refs()
        available <- vapply(correction_model()$candidates,`[[`,character(1L),'candidate_ref')
        # Die Reihe darf weitergehen, ohne dass der Eigentuemer das Verwerfen
        # erneut bestaetigt: "unveraendert lassen" ist die Bestaetigung (#424).
        # Nach einem geschriebenen Schritt ist nichts Ungespeichertes mehr zu
        # schuetzen: Die Freigabe verwirft, ohne zu fragen.
        result <- activity_workflow$select(runtime_context_fingerprint(runtime$context),refs,available,
          isTRUE(input$activity_selection_discard) || reihe_verwerfen || isTRUE(released))
        if (identical(result$status,'discard_required')) stop('Nicht gespeicherte Eingaben bleiben erhalten. Zum Auswahlwechsel zuerst das Verwerfen bestätigen.',call.=FALSE)
        activity_workflow_loading <<- NULL
        activity_workflow_completed(FALSE)
        activity_preview(NULL);correction_preview(NULL);activity_completed(NULL);activity_approval(NULL)
        shiny::updateCheckboxInput(session,'activity_correction_confirm',value=FALSE)
        action_feedback$clear('activity')
        activity_workflow_view(activity_workflow$view())
        result
      },error=function(error){state(list(tone='warning',title='Auswahl nicht übernommen',copy=conditionMessage(error)));NULL})
      if (is.null(selected)) return()
      refs <- activity_workflow$view()$selected_refs
      if (length(refs)) activity_workflow_reset_pending <<- FALSE
      if (!length(refs)) {
        if (!identical(selected$status,'unchanged') || activity_workflow_reset_pending || isTRUE(input$activity_selection_discard)) {
          activity_workflow_reset_pending <<- TRUE
          shiny::updateSelectInput(session,'activity_type',selected='buy')
          shiny::updateSelectInput(session,'activity_amount_mode',selected='quantity_unit_price')
          shiny::updateSelectInput(session,'activity_basis_mode',selected='derived_trade')
          shiny::updateSelectInput(session,'activity_acquisition_evidence',selected='not_applicable')
          shiny::updateSelectInput(session,'activity_movement_context',selected='not_applicable')
          shiny::updateSelectInput(session,'activity_source_asset',selected='')
          shiny::updateSelectInput(session,'activity_related_account',selected='')
          shiny::updateTextInput(session,'activity_utc',value='')
          for (id in c('activity_quantity','activity_eligible_quantity','activity_unit_price','activity_gross_total','activity_net_total','activity_net_unit_price','activity_monetary_fee','activity_asset_fee','activity_provided_basis')) shiny::updateTextInput(session,id,value='')
        }
        shiny::updateCheckboxInput(session,'activity_selection_discard',value=FALSE)
        # Sind die Betraege schon leer, meldet der Browser nichts zurueck, und
        # das Zuruecksetzen bliebe offen: Die erste eingetippte Menge galt dann
        # als "noch nicht zurueckgesetzt", und die Neuanlage war gesperrt.
        tryCatch(sync_activity_workflow(), error=function(error) NULL)
        state(list(tone='neutral',title='Neuanlage ausgewählt',copy='Keine bestehende Buchung wird geändert. Portfolio und Konto bleiben als Arbeitskontext erhalten.'))
        return()
      }
      if (length(refs)>1L) {
        shiny::updateCheckboxInput(session,'activity_selection_discard',value=FALSE)
        shiny::updateSelectInput(session,'activity_correction_action',choices=c('Ausgewählte Buchungen stornieren'='void'),selected='void')
        state(list(tone='warning',title='Mehrere Buchungen ausgewählt',copy=paste(length(refs),'Buchungen · gemeinsam stornieren oder mit „Einzeln durchgehen“ eine nach der anderen bearbeiten. Beim gemeinsamen Storno zuerst alle Buchungen und FIFO-/Verwahrfolgen prüfen, danach ausdrücklich bestätigen.')))
        return()
      }
      activity_workflow$set_action('correct')
      request <- activity_workflow$begin_load(isTRUE(input$activity_selection_discard) || reihe_verwerfen)
      if (identical(request$status,'discard_required')) {state(list(tone='warning',title='Entwurf bleibt erhalten',copy='Vor erneutem Laden das Verwerfen der nicht gespeicherten Eingaben bestätigen.'));return()}
      shiny::updateCheckboxInput(session,'activity_selection_discard',value=FALSE)
      shiny::updateSelectInput(session,'activity_correction_action',choices=c('Bearbeiten'='correct','Stornieren'='void'),selected='correct')
      ref <- refs[[1L]]
      safe(data_asset_activity_correction_prefill_v1(correction_center,activity_editor,runtime$context,ref),function(form){
        activity_workflow_loading <<- list(ticket=request$ticket,form=form)
        activity_workflow_view(activity_workflow$view())
        shiny::updateSelectInput(session,"activity_type",selected=form$event_type);shiny::updateSelectInput(session,"activity_portfolio",selected=form$portfolio_ref);activity_asset_update(selected=form$asset_ref)
        refresh_activity_account_choices();shiny::updateSelectInput(session,"activity_account",selected=form$account_ref);shiny::updateSelectInput(session,"activity_related_account",selected=form$related_account_ref);shiny::updateSelectInput(session,"activity_source_asset",selected=form$source_asset_ref)
        shiny::updateSelectInput(session,"activity_time_evidence",selected=form$event_time_evidence);shiny::updateDateInput(session,"activity_date",value=as.Date(form$local_date));shiny::updateTextInput(session,"activity_time",value=form$local_time);shiny::updateTextInput(session,"activity_zone",value=form$time_zone);shiny::updateTextInput(session,"activity_utc",value=form$effective_at_utc)
        shiny::updateSelectInput(session,"activity_amount_mode",selected=form$amount_input_mode);shiny::updateSelectInput(session,"activity_basis_mode",selected=form$basis_evidence_mode);shiny::updateTextInput(session,"activity_quantity",value=form$quantity_decimal);shiny::updateTextInput(session,"activity_eligible_quantity",value=form$eligible_quantity_decimal);shiny::updateTextInput(session,"activity_unit_price",value=form$unit_price_decimal);shiny::updateTextInput(session,"activity_gross_total",value=form$gross_amount_decimal);shiny::updateTextInput(session,"activity_monetary_fee",value=form$monetary_fee_decimal);shiny::updateTextInput(session,"activity_asset_fee",value=form$asset_fee_quantity_decimal);shiny::updateTextInput(session,"activity_provided_basis",value=form$provided_basis_decimal);shiny::updateSelectInput(session,"activity_movement_context",selected=form$movement_context_code)
        shiny::updateSelectInput(session,"activity_acquisition_evidence",selected=form$original_acquired_time_evidence);if(nzchar(form$original_acquired_local_date))shiny::updateDateInput(session,"activity_acquisition_date",value=as.Date(form$original_acquired_local_date));shiny::updateTextInput(session,"activity_acquisition_time",value=form$original_acquired_local_time);shiny::updateTextInput(session,"activity_acquisition_zone",value=form$original_acquired_time_zone);shiny::updateTextInput(session,"activity_acquisition_utc",value=form$original_acquired_at_utc)
        sync_activity_workflow()
        state(list(tone="warning",title="Vorgänger als Korrekturentwurf geladen",copy="Noch kein Schreiben. Werte in der gemeinsamen Maske bearbeiten oder Storno ohne Ersatz wählen."))
      })
  }
  # Nach einer geschriebenen Korrektur oder einem Storno zurueck zur Neuanlage.
  # Die Maske verschwand nach dem Storno, und auch neues Laden half nicht. Die Werte
  # der bearbeiteten Buchung bleiben dabei nicht fuer eine aehnliche stehen.
  #
  # Der Server gibt die Auswahl selbst frei, statt den Browser um das Leeren zu
  # bitten: Eine Rueckmeldung des Browsers liefe durch dieselben Beobachter wie
  # ein Klick des Eigentuemers und loeschte die Meldung ueber den Schritt, der
  # eben geschrieben wurde. Gelingt die Freigabe nicht, bleibt der bisherige
  # Stand "Korrektur/Storno abgeschlossen" stehen.
  activity_release_selection <- function() {
    stale <- input$activity_rows_selected
    stale <- if (is.null(stale)) character() else sort(as.character(stale[nzchar(as.character(stale))]))
    activity_rows_released(stale)
    activity_apply_selection(released = TRUE)
    if (isTRUE(activity_workflow_completed())) {
      activity_rows_released(character())
      return(FALSE)
    }
    # Der Arbeitskontext kommt wieder aus dem Asset-Center. Erzwungen, weil die
    # Betraege der bearbeiteten Buchung in diesem Durchlauf noch in input$ stehen.
    tryCatch(invisible(refresh_activity_catalog(force_context = TRUE, reuse = TRUE)), error = function(error) NULL)
    TRUE
  }
  # Die Meldung bleibt, bis der Eigentuemer das Naechste beginnt: eine Zeile
  # waehlt, eine Buchung prueft, das Asset wechselt oder die Liste neu liest.
  shiny::observeEvent(list(input$activity_rows_selected, input$activity_prepare, input$activity_correction_refresh,
    input$asset_center_asset, input$activity_draft_discard), activity_release_notice(NULL), ignoreInit = TRUE, ignoreNULL = FALSE)
  output$activity_release_feedback <- shiny::renderUI(data_action_feedback_panel_v1(activity_release_notice()))
  action_feedback$observe("correction", input$activity_correction_load, activity_apply_selection())
  # Auf die Auswahl in der Tabelle reagieren, nicht nur auf den Knopf. ignoreNULL
  # bleibt aus, damit auch das Leeren der Auswahl greift - dann soll das Formular
  # zur Neuanlage zurueckkehren.
  action_feedback$observe("correction", input$activity_rows_selected,
    activity_apply_selection(), ignoreInit = TRUE, ignoreNULL = FALSE)
  # "Auswahl leeren" waehrend eines Durchgangs beendet ihn. Waehrend die Reihe
  # laeuft, fuehrt sie die Auswahl - ein geleertes Kaestchen waere sonst ohne
  # Wirkung, und der Eigentuemer saesse in einer Reihe, die er leeren wollte.
  shiny::observeEvent(input$activity_rows_selected, {
    reihe <- activity_sequence()
    if (is.null(reihe)) return(invisible(NULL))
    gemeldet <- input$activity_rows_selected
    if (length(gemeldet) && any(nzchar(as.character(gemeldet)))) return(invisible(NULL))
    activity_sequence(NULL)
    activity_sequence_report(list(status='stopped', total=length(reihe$keys), outcomes=reihe$outcomes))
  }, ignoreInit = TRUE, ignoreNULL = FALSE, priority = 110)
  # Ruecke die Reihe weiter, uebernimmt die naechste Buchung von selbst. Der
  # Browser meldet dabei nichts: die Auswahl der Reihe liegt im Server (#424).
  # Nur beim Weiterruecken, nicht beim Ende: Lauft die Reihe aus, bleibt die
  # Meldung des letzten Schrittes stehen, so wie nach einer einzelnen Korrektur.
  action_feedback$observe("correction", activity_sequence(),
    if (!is.null(activity_sequence())) activity_apply_selection(),
    ignoreInit = TRUE, ignoreNULL = FALSE)
  action_feedback$observe('correction', input$activity_correction_prepare, {
    safe({
      action <- input$activity_correction_action
      view <- require_activity_workflow(action)
      activity_workflow_ticket <<- activity_workflow$begin_preview()$ticket
      form <- if (identical(action,'void')) NULL else activity_form()
      scale <- if (identical(action,'void')) list(status='not_required') else data_asset_quantity_scale_prepare_for_activity_v1(
        scale_center, activity_editor, runtime$context, form, now_utc()
      )
      if (identical(scale$status, "ready_for_confirmation")) {
        list(kind="scale", value=scale)
      } else {
        list(kind="correction", value=data_asset_activity_correction_prepare_v1(
          correction_center, activity_editor, runtime$context,
          view$selected_refs, action,
          form, now_utc()
        ))
      }
    }, function(prepared) {
      shiny::updateCheckboxInput(session,"activity_correction_confirm",value=FALSE)
      shiny::updateCheckboxInput(session,"activity_scale_confirm",value=FALSE)
      if (identical(prepared$kind, "scale")) {
        correction_preview(NULL); scale_preview(prepared$value)
        state(list(
          tone="warning", title="Feinere Mengenskala vor Korrektur erforderlich",
          copy=prepared$value$warning_text
        ))
      } else {
        if (!activity_workflow$accept_preview(activity_workflow_ticket,prepared$value)) stop('activity_workflow_preview_stale',call.=FALSE)
        activity_workflow_view(activity_workflow$view())
        scale_preview(NULL); correction_preview(prepared$value)
        preview <- prepared$value
        state(list(
          tone="warning", title="Korrektur-/Storno-Vorschau bereit",
          copy=paste(
            "Aktion:",preview$action_type,"· betroffene FIFO-Welten:",
            preview$affected_fifo_world_count,"· Vorgänger bleibt erhalten."
          )
        ))
      }
    })
  })
  shiny::observeEvent(input$activity_correction_confirm, {
    preview<-correction_preview();correction_approval(if(isTRUE(input$activity_correction_confirm)&&!is.null(preview))preview$preview_ref else NULL)
  },ignoreInit=TRUE)
  action_feedback$observe('correction', input$activity_correction_execute,{
    ready <- tryCatch({require_activity_workflow(input$activity_correction_action);!is.null(activity_workflow$prepared()) && identical(activity_workflow$prepared(),correction_preview())},error=function(error)FALSE)
    if (!ready) {state(list(tone='warning',title='Korrektur blockiert',copy='Auswahl, Aktion oder Formular passen nicht mehr zur Vorschau. Zuerst Auswahl übernehmen und erneut prüfen.'));return()}
    preview<-correction_preview();if(is.null(preview)||!isTRUE(input$activity_correction_confirm)||!identical(correction_approval(),preview$preview_ref)){state(list(tone="error",title="Korrektur blockiert",copy=pl_error_text_v1("data_asset_activity_correction_confirmation_required")));return()}
    correction_approval(NULL)
    activity_workflow$revoke();activity_workflow_view(activity_workflow$view())
    safe({data_asset_activity_correction_confirm_v1(correction_center,preview$preview_ref,runtime$context);issued<-now_utc();data_asset_activity_correction_execute_v1(correction_center,runtime$context,preview$preview_ref,issued,add_seconds(issued,300L))},function(result){
      activity_workflow$mark_saved();activity_workflow_view(activity_workflow$view())
      activity_workflow_completed(TRUE)
      correction_preview(NULL);shiny::updateCheckboxInput(session,"activity_correction_confirm",value=FALSE);invisible(refresh_activity_catalog());invisible(refresh_activity_corrections());materialized<-update_realized_state("incremental")
      # In einer Reihe geht es nach dem geschriebenen Schritt von selbst weiter.
      reihe_davor <- activity_sequence()
      activity_sequence_advance(if (identical(result$action_type,'void')) 'voided' else 'corrected')
      asset_maintenance_refresh()
      # Ausserhalb einer laufenden Reihe ist die Arbeit an dieser Auswahl beendet.
      in_reihe <- !is.null(reihe_davor)
      released <- is.null(activity_sequence()) && activity_release_selection()
      meldung <- list(tone=if(is.null(materialized))"warning"else"neutral",title=if(identical(result$action_type,'void'))if(!is.null(preview$selected_event_count))paste(preview$selected_event_count,'Buchungen gemeinsam storniert')else'Buchung storniert'else'Buchung korrigiert',copy=paste(c(
        paste("Vorgänger unveränderlich erhalten · Ersatzereignisse:",result$replacement_event_count,"· FIFO-Stand",if(is.null(materialized))"veraltet"else"aktualisiert","· Cash 0."),
        if(released)"Die Maske steht wieder auf Neuanlage."),collapse=" "))
      state(meldung)
      # Nach der Freigabe traegt die eigene Meldung; der Kanal der Korrektur waere
      # mit der ersten Rueckmeldung der geleerten Felder wieder leer. Am Ende einer
      # Reihe sagt deren Bericht, was geschehen ist.
      if (released) {
        action_feedback$clear('correction')
        activity_release_notice(if (in_reihe) NULL else meldung)
      }
    })
  })
  # Reihe beginnen: die gewaehlten Buchungen in Tabellenreihenfolge, neueste
  # zuerst. Die Tabelle stellt danach jeweils genau eine Zeile als Auswahl, und
  # der bestehende Weg Vorschau - Bestaetigung - Anwenden gilt unveraendert.
  action_feedback$observe('correction', input$activity_sequence_start, {
    refs <- workflow_refs()
    daten <- activity_rows_frame()
    model <- correction_model()
    if (length(refs) < 2L || is.null(daten) || is.null(model)) {
      state(list(tone='warning', title='Reihe nicht möglich',
        copy='Für einen Durchgang mindestens zwei Buchungen in der Tabelle wählen.')); return()
    }
    nach_ref <- list()
    for (row in model$candidates) nach_ref[[as.character(row$candidate_ref)]] <- row
    geordnet <- daten$keys[daten$keys %in% refs]
    keys <- vapply(geordnet, function(ref) {
      row <- nach_ref[[ref]]
      if (is.null(row)) NA_character_ else activity_sequence_key(row)
    }, character(1L))
    if (anyNA(keys) || length(keys) != length(refs)) {
      state(list(tone='warning', title='Reihe nicht möglich',
        copy='Die Auswahl passt nicht mehr zur gelesenen Buchungsliste. Zuerst „Buchungen neu lesen“.')); return()
    }
    activity_sequence_report(NULL)
    activity_sequence_discard(TRUE)
    activity_sequence(list(keys=unname(keys), index=1L, outcomes=character()))
    state(list(tone='warning', title=paste('Durchgang über', length(keys), 'Buchungen begonnen'),
      copy='Jede Buchung steht einzeln in der Maske. Ändern und bestätigen, stornieren oder unverändert lassen; danach geht es von selbst weiter.'))
  })
  action_feedback$observe('correction', input$activity_sequence_skip, {
    if (is.null(activity_sequence())) {
      state(list(tone='warning', title='Keine Reihe offen', copy='Es läuft kein Durchgang.')); return()
    }
    activity_sequence_advance('unchanged')
    reihe <- activity_sequence()
    state(list(tone='neutral', title='Buchung unverändert gelassen',
      copy=if (is.null(reihe)) 'Der Durchgang ist beendet.'
        else paste('Weiter bei Buchung', reihe$index, 'von', length(reihe$keys), '· nichts geschrieben.')))
  })
  action_feedback$observe('correction', input$activity_sequence_stop, {
    reihe <- activity_sequence()
    if (is.null(reihe)) {
      state(list(tone='warning', title='Keine Reihe offen', copy='Es läuft kein Durchgang.')); return()
    }
    activity_sequence(NULL)
    activity_sequence_report(list(status='stopped', total=length(reihe$keys), outcomes=reihe$outcomes))
    state(list(tone='neutral', title='Durchgang beendet',
      copy=paste('Abgebrochen bei Buchung', reihe$index, 'von', length(reihe$keys),
        '· bereits geschriebene Änderungen bleiben, die übrigen Buchungen sind unberührt.')))
  })
  shiny::observeEvent(input$portfolio_completion_check, safe(
    {model<-refresh_realized_state();invisible(refresh_activity_catalog());model},
    function(value){portfolio_completion_notice(NULL);state(list(tone=if(identical(value$freshness,"fresh"))"neutral"else"warning",title="Rechenstand geprüft",copy=paste("Rechenstand",realized_freshness_label(value$freshness),"·",value$world_count,"gerechnete Assets · kein Kursabruf")))}
  ))
  shiny::observeEvent(input$portfolio_completion_update, {
    if(!isTRUE(input$portfolio_completion_confirm)){state(list(tone="warning",title="Bestätigung fehlt",copy="Bitte das Häkchen „Betroffene Assets jetzt nachrechnen“ neben „Nachrechnen“ setzen."));return()}
    safe(update_realized_state("incremental",tolerate_failure=FALSE),function(value){shiny::updateCheckboxInput(session,"portfolio_completion_confirm",value=FALSE);portfolio_completion_notice(NULL);invisible(refresh_activity_catalog());state(list(tone="neutral",title="Nachgerechnet",copy=paste(value$changed_world_count,"Assets neu gerechnet ·",value$reused_world_count,"unverändert übernommen")))})
  })
  # Auch die Bereitschaft wurde nur auf Klick gelesen. Sie ist abfragefrei und
  # startet keinen Worker, also laedt sie beim Start und beim Wechsel in den
  # Transaktions-Tab von selbst (#189/#283, 21.09.2026). Nur die Matrix wird
  # gelesen: Ein automatischer voller State-Lauf verwirft laufende Entwuerfe.
  readiness_autoload <- function() {
    tryCatch(readiness_model(realized_adapter$readiness(runtime$context)), error = function(error) invisible(NULL))
  }
  shiny::observeEvent(TRUE, readiness_autoload(), once = TRUE)
  shiny::observeEvent(input$asset_center_step, {
    if (identical(input$asset_center_step, "transactions")) readiness_autoload()
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$realized_state_full, safe(
    update_realized_state("full_rebuild",tolerate_failure=FALSE),
    function(value) state(list(tone="neutral", title="Komplett neu gerechnet", copy=paste(value$world_count, "Assets aus allen Buchungen neu gerechnet.")))
  ))
  shiny::observeEvent(input$realized_state_verify, safe(
    realized_adapter$verify(runtime$context),
    function(value) { realized_parity(value); state(list(tone="neutral", title="Gegenprüfung bestanden", copy=paste(value$world_count, "Assets: Fortschreibung und vollständige Neurechnung stimmen genau überein."))) }
  ))
  action_feedback$observe('import', input$activity_quick_inspect,{
    file<-input$activity_quick_file
    if(is.null(file)||nrow(file)!=1L){state(list(tone="error",title="Quick Import blockiert",copy=pl_error_text_v1("data_activity_quick_import_source_required")));return()}
    safe(data_activity_quick_inspect_v1(activity_quick_center,runtime$context,file$datapath[[1L]]),function(model){activity_quick_inspection(model);activity_quick_prepared(NULL);activity_quick_loaded_profile(NULL);shiny::updateCheckboxInput(session,"activity_quick_confirm",value=FALSE);state(list(tone=if(model$blocked_row_count)"error"else if(model$needs_input_row_count)"warning"else"neutral",title="Tolerante Buchungsdatei geprüft",copy=paste(model$activity_row_count,"Zeilen mit Buchungen · ausdrückliche Zuordnung:",model$portfolio_mapping_key_count,"Portfolio-,",model$account_mapping_key_count,"Konto- und",model$asset_mapping_key_count,"Asset-Schlüssel · noch kein Schreiben in die Stammdaten.")))})
  })
  action_feedback$observe('profile', input$activity_quick_profile_refresh,safe(refresh_activity_quick_profiles(),function(model)state(list(tone="neutral",title="Zuordnungsprofile gelesen",copy=paste(model$profile_count,"an den Kontext gebundene Profile · kein Schreiben in die Stammdaten.")))))
  action_feedback$observe('profile', input$activity_quick_profile_load,{
    if(is.null(activity_quick_inspection())){state(list(tone="error",title="Zuordnungsprofil blockiert",copy="Zuerst die Zieldatei prüfen, damit alle Quellschlüssel sichtbar sind."));return()}
    handle<-input$activity_quick_profile_select;if(is.null(handle)||!nzchar(handle)){state(list(tone="error",title="Zuordnungsprofil blockiert",copy=pl_error_text_v1("data_activity_quick_import_mapping_required")));return()}
    safe(data_activity_quick_mapping_profile_load_v1(activity_quick_center,runtime$context,handle),function(loaded){apply_activity_quick_profile(loaded);shiny::updateTextInput(session,"activity_quick_profile_label",value=loaded$public_profile$profile_label);shiny::updateCheckboxInput(session,"activity_quick_profile_standard",value=isTRUE(loaded$public_profile$is_standard));state(list(tone="neutral",title="Zuordnungsprofil geladen",copy="Alle Ziele wurden gegen das aktuelle Register erneut auf browserlokale Verweise aufgelöst."))})
  })
  action_feedback$observe('profile', input$activity_quick_profile_save,{
    if(is.null(activity_quick_inspection())){state(list(tone="error",title="Zuordnungsprofil blockiert",copy="Zuerst eine tolerante Datei prüfen und alle Schlüssel zuordnen."));return()}
    safe({profile<-new_data_activity_quick_mapping_profile_v1(runtime$context,input$activity_quick_portfolio,input$activity_quick_default_account,portfolio_mappings=activity_quick_mapping_entries("portfolios"),account_mappings=activity_quick_mapping_entries("accounts"),asset_mappings=activity_quick_mapping_entries("assets"));data_activity_quick_mapping_profile_save_v1(activity_quick_center,runtime$context,profile,input$activity_quick_profile_label,isTRUE(input$activity_quick_profile_standard),now_utc())},function(saved){invisible(refresh_activity_quick_profiles());state(list(tone="neutral",title="Zuordnungsprofil gespeichert",copy=paste(saved$profile_label,"· Fassung",saved$revision,"· nur im aktiven Registerkontext.")))})
  })
  action_feedback$observe('import', input$activity_quick_prepare,{
    if(is.null(activity_quick_inspection())){state(list(tone="error",title="Quick Import blockiert",copy=pl_error_text_v1("data_activity_quick_import_source_required")));return()}
    safe({profile<-new_data_activity_quick_mapping_profile_v1(runtime$context,input$activity_quick_portfolio,input$activity_quick_default_account,portfolio_mappings=activity_quick_mapping_entries("portfolios"),account_mappings=activity_quick_mapping_entries("accounts"),asset_mappings=activity_quick_mapping_entries("assets"));data_activity_quick_prepare_v1(activity_quick_center,runtime$context,profile,now_utc())},function(model){activity_quick_prepared(model);shiny::updateCheckboxInput(session,"activity_quick_confirm",value=FALSE);state(list(tone=if(model$blocked_row_count)"error"else if(model$needs_input_row_count)"warning"else"neutral",title="Buchungsentwürfe mit ausdrücklicher Schlüsselzuordnung vorbereitet",copy=paste(model$ready_row_count,"bereit ·",model$needs_input_row_count,"Angaben fehlen ·",model$blocked_row_count,"blockiert · an das Register des Eigentümers gebunden.")))})
  })
  action_feedback$observe('import', input$activity_quick_execute,{
    if(is.null(activity_quick_prepared())||!isTRUE(input$activity_quick_confirm)){state(list(tone="error",title="Quick Import blockiert",copy=pl_error_text_v1("data_activity_quick_import_confirmation_required")));return()}
    safe(data_activity_quick_import_ready_v1(activity_quick_center,runtime$context,TRUE,now_utc()),function(result){shiny::updateCheckboxInput(session,"activity_quick_confirm",value=FALSE);activity_quick_prepared(NULL);invisible(refresh_activity_catalog());invisible(refresh_activity_corrections());invisible(refresh_activity_drafts());materialized<-update_realized_state("incremental");state(list(tone=if(result$needs_input_row_count||result$blocked_row_count||result$applying_row_count||is.null(materialized))"warning"else"neutral",title="Bereite Zeilen importiert",copy=paste(result$created_row_count,"neu ·",result$already_committed_row_count,"bereits übernommen ·",result$deduplicated_row_count,"bereits als Entwurf gebunden ·",result$needs_input_row_count,"Angaben fehlen ·",result$blocked_row_count,"blockiert ·",result$applying_row_count,"in Wiederaufnahme · Cash/Kursanbieter 0 · FIFO-Stand",if(is.null(materialized))"veraltet"else"aktualisiert")))})
  })
  shiny::observeEvent(input$activity_draft_refresh,safe(refresh_activity_drafts(),function(model)state(list(tone=if(length(model$drafts))"warning"else"neutral",title="Entwürfe gelesen",copy=paste0(length(model$drafts)," offen von ",model$draft_count," Entwürfen · gebuchte und abgelöste stehen nicht in der Liste; interne IDs und Pfade bleiben verborgen.")))))
  # Gruende der blockierten offenen Entwuerfe (#420): ein lesender Aufruf fuer alle, hoechstens 200.
  shiny::observeEvent(input$activity_draft_reasons_run,{
    model<-activity_draft_list();rows<-if(is.list(model))Filter(function(row)identical(row$status,"validated_blocked"),model$drafts)else list()
    if(!length(rows)){state(list(tone="neutral",title="Keine blockierten Entwürfe",copy=if(is.list(model))"Unter den offenen Entwürfen ist keiner blockiert."else"Zuerst „Offene Entwürfe laden“."));return()}
    shown<-utils::head(rows,200L)
    safe(shiny::withProgress(message="Gründe werden gelesen",value=NULL,
      data_activity_draft_block_reasons_v1(activity_draft_center,activity_editor,runtime$context,vapply(shown,`[[`,character(1L),"draft_handle"))),
      function(reasons){activity_draft_reasons(reasons);state(list(tone="neutral",title="Gründe gelesen",copy=sprintf("%d blockierte Entwürfe; der Grund steht in der Tabelle.",length(reasons))))})
  },ignoreInit=TRUE)
  action_feedback$observe('draft', input$activity_draft_select,{
    activity_draft_approval(NULL);shiny::updateCheckboxInput(session,'activity_draft_confirm',value=FALSE)
    if(is.null(input$activity_draft_select)||!nzchar(input$activity_draft_select)) {
      activity_draft_open(activity_draft_completed())
      if(is.null(activity_draft_completed()))action_feedback$clear('draft')
      return()
    }
    action_feedback$clear('draft');activity_draft_completed(NULL);activity_draft_open(NULL)
    safe(data_activity_draft_open_v1(activity_draft_center,activity_editor,runtime$context,input$activity_draft_select),function(model){activity_draft_open(model)
      batch<-!is.null(model$batch_preview);recovery<-batch&&identical(model$status,'applying')
      shiny::updateCheckboxInput(session,'activity_draft_confirm',label=if(recovery)'Gespeicherte Auswahl und gemeinsame Vorschau geprüft: dieselbe Storno-Auswahl jetzt erneut freigeben'else'Diesen validierten Entwurf einmalig bestätigen',value=FALSE)
      shiny::updateActionButton(session,'activity_draft_commit',label=if(recovery)'Bestätigte Wiederaufnahme des Sammellaufs'else'Validierten Entwurf übernehmen')
      shiny::updateActionButton(session,'activity_draft_resume',label=if(batch)'Nur aktiven Beleg des Sammellaufs abgleichen'else'Unterbrochenen Entwurf fortsetzen')
      fields<-unique(c(intersect(model$missing_fields,.data_activity_draft_editable_fields_v1()),.data_activity_draft_editable_fields_v1()));shiny::updateSelectInput(session,"activity_draft_field",choices=stats::setNames(fields,fields),selected=fields[[1L]]);shiny::updateCheckboxInput(session,"activity_draft_confirm",value=FALSE)})
  },ignoreInit=TRUE)
  shiny::observeEvent(input$activity_draft_field,{
    field<-input$activity_draft_field;if(is.null(field)||!nzchar(field))return()
    choices<-c("Wert setzen"="set_value","Als fehlend markieren"="remove");if(field%in%.data_activity_draft_nullable_fields_v1())choices<-c("Wert setzen"="set_value","Explizit nicht anwendbar"="set_null","Als fehlend markieren"="remove")
    shiny::updateSelectInput(session,"activity_draft_operation",choices=choices,selected="set_value")
  },ignoreInit=TRUE)
  action_feedback$observe('draft', input$activity_draft_patch,{
    model<-activity_draft_open();if(is.null(model)){state(list(tone="error",title="Bearbeitung des Entwurfs blockiert",copy=pl_error_text_v1("data_activity_draft_handle_invalid")));return()}
    field<-input$activity_draft_field;identity<-field%in%c("account_ref","related_account_ref","asset_ref","source_asset_ref");value<-if(identity)input$activity_draft_value_ref else input$activity_draft_value_text
    safe(data_activity_draft_patch_field_v1(activity_draft_center,activity_editor,runtime$context,model$draft_handle,field,input$activity_draft_operation,value,now_utc()),function(updated){activity_draft_open(data_activity_draft_open_v1(activity_draft_center,activity_editor,runtime$context,model$draft_handle));shiny::updateCheckboxInput(session,"activity_draft_confirm",value=FALSE);state(list(tone="warning",title="Feld des Entwurfs gespeichert",copy=paste("Fassung",updated$revision,"· vor dem Schreiben erneut validieren.")))})
  })
  action_feedback$observe('draft', input$activity_draft_valuation_apply,{
    model<-activity_draft_open();if(is.null(model)||!identical(model$valuation_summary$lifecycle,"valuation_pending")){state(list(tone="error",title="Bewertung blockiert",copy=pl_error_text_v1("data_activity_draft_input_invalid")));return()}
    safe(data_activity_draft_set_manual_reward_valuation_v1(activity_draft_center,statement_mapping_center,runtime$context,model$draft_handle,input$activity_draft_valuation_mode,input$activity_draft_valuation_value,input$activity_draft_valuation_currency,now_utc()),function(updated){activity_draft_open(data_activity_draft_open_v1(activity_draft_center,activity_editor,runtime$context,model$draft_handle));shiny::updateCheckboxInput(session,"activity_draft_confirm",value=FALSE);state(list(tone="warning",title="Manuelle Reward-Bewertung gespeichert",copy=paste("Fassung",updated$revision,"· Bewertungsherkunft: manuell durch den Eigentümer · erneut validieren.")))})
  })
  action_feedback$observe('draft', input$activity_draft_revalidate,{
    model<-activity_draft_open();if(is.null(model)){state(list(tone="error",title="Validierung des Entwurfs blockiert",copy=pl_error_text_v1("data_activity_draft_handle_invalid")));return()}
    safe(data_activity_draft_revalidate_v1(activity_draft_center,activity_editor,runtime$context,model$draft_handle,now_utc()),function(validated){activity_draft_open(data_activity_draft_open_v1(activity_draft_center,activity_editor,runtime$context,model$draft_handle));shiny::updateCheckboxInput(session,"activity_draft_confirm",value=FALSE);state(list(tone=if(identical(validated$validation_status,"ready"))"neutral"else"warning",title="Entwurf erneut validiert",copy=paste("Status:",validated$validation_status,"· fehlende Felder:",length(validated$missing_fields))))})
  })
  action_feedback$observe('draft', input$activity_draft_fee_resolve,{
    model<-activity_draft_open();if(is.null(model)||!isTRUE(model$can_resolve_unclassified_fee)){state(list(tone="error",title="Gebührenrolle blockiert",copy=pl_error_text_v1("data_activity_draft_input_invalid")));return()}
    safe(data_activity_draft_resolve_unclassified_fee_v1(activity_draft_center,runtime$context,model$draft_handle,input$activity_draft_fee_role,now_utc()),function(updated){activity_draft_open(data_activity_draft_open_v1(activity_draft_center,activity_editor,runtime$context,model$draft_handle));shiny::updateCheckboxInput(session,"activity_draft_confirm",value=FALSE);state(list(tone="warning",title="Gebührenrolle gespeichert",copy=paste("Exakter Quellwert",updated$unclassified_fee_summary$decimal,"als",updated$unclassified_fee_summary$status,"gebunden · erneut validieren.")))})
  })
  action_feedback$observe('draft', input$activity_draft_resume,{
    model<-activity_draft_open();if(is.null(model)||!identical(model$draft_handle,input$activity_draft_select)||!isTRUE(model$can_resume)){state(list(tone="error",title="Wiederaufnahme des Entwurfs blockiert",copy=pl_error_text_v1("activity_draft_state_conflict")));return()}
    safe(data_activity_draft_resume_v1(activity_draft_center,runtime$context,model$draft_handle),function(receipt){completed<-data_activity_draft_open_v1(activity_draft_center,activity_editor,runtime$context,model$draft_handle);activity_draft_completed(completed);activity_draft_open(completed);invisible(refresh_activity_catalog());invisible(refresh_activity_corrections());invisible(refresh_activity_drafts());materialized<-update_realized_state("incremental");state(list(tone=if(is.null(materialized))"warning"else"neutral",title="Wiederaufnahme des Buchungsentwurfs abgeschlossen",copy=paste(if(!is.null(model$batch_preview))'Aktiver Batchbeleg abgeglichen – keine erneute Buchung.'else'Bestehender Attempt verwendet.',receipt$draft_status,'· FIFO-Stand',if(is.null(materialized))'stale'else'aktualisiert')))})
  })
  shiny::observeEvent(input$activity_draft_confirm, {
    model<-activity_draft_open();activity_draft_approval(if(isTRUE(input$activity_draft_confirm)&&!is.null(model))list(model$draft_handle,model$revision)else NULL)
  },ignoreInit=TRUE)
  action_feedback$observe('draft', input$activity_draft_commit,{
    model<-activity_draft_open();if(is.null(model)||!identical(model$draft_handle,input$activity_draft_select)||!isTRUE(model$can_confirm)||!isTRUE(input$activity_draft_confirm)||!identical(activity_draft_approval(),list(model$draft_handle,model$revision))){state(list(tone="error",title="Übernahme des Entwurfs blockiert",copy=pl_error_text_v1("data_activity_draft_confirmation_required")));return()}
    activity_draft_approval(NULL);shiny::updateCheckboxInput(session,'activity_draft_confirm',value=FALSE)
    safe({at<-now_utc();invisible(data_activity_draft_confirm_v1(activity_draft_center,runtime$context,model$draft_handle,at));data_activity_draft_execute_v1(activity_draft_center,runtime$context,model$draft_handle,at)},function(receipt){completed<-data_activity_draft_open_v1(activity_draft_center,activity_editor,runtime$context,model$draft_handle);activity_draft_completed(completed);activity_draft_open(completed);shiny::updateCheckboxInput(session,"activity_draft_confirm",value=FALSE);invisible(refresh_activity_catalog());invisible(refresh_activity_corrections());invisible(refresh_activity_drafts());materialized<-update_realized_state("incremental");state(list(tone=if(is.null(materialized))"warning"else"neutral",title="Buchungsentwurf übernommen",copy=paste("Status:",receipt$draft_status,"· Cash/Kursanbieter 0 · FIFO-Stand",if(is.null(materialized))"veraltet"else"aktualisiert")))})
  })
  # CSV exchange (#361, #191): check, then preview directly when no mapping is needed.
  activity_csv_mapping_values<-function(model){values<-list();for(index in seq_along(model$asset_mappings))values[[sprintf("activity_csv_asset_mapping_%03d",index)]]<-input[[sprintf("activity_csv_asset_mapping_%03d",index)]];for(index in seq_along(model$account_mappings))values[[sprintf("activity_csv_account_mapping_%03d",index)]]<-input[[sprintf("activity_csv_account_mapping_%03d",index)]];values}
  activity_csv_run_preview<-function(model,values=list())safe({mapping<-data_asset_activity_csv_default_mapping_v1(model,values);data_asset_activity_csv_prepare_v1(activity_csv_center,runtime$context,mapping,now_utc())},function(preview){
    activity_csv_preview(preview)
    state(switch(preview$status,
      ready_for_confirmation=list(tone="warning",title="CSV-Vorschau bereit",copy=data_asset_activity_csv_ready_text_v1(preview)),
      nothing_to_import=list(tone="neutral",title="Nichts zu übernehmen",copy=paste("Alle",preview$unchanged_row_count,"Zeilen sind bereits gebucht; der Datenbestand bleibt unverändert.")),
      list(tone="error",title="CSV-Import blockiert",copy=paste(preview$blocked_row_count,"Zeile(n) mit Fehler – Gründe stehen in der Tabelle. Es wurde nichts übernommen."))))
  })
  shiny::observeEvent(input$activity_csv_inspect,{
    file<-input$activity_csv_file;if(is.null(file)||nrow(file)!=1L){state(list(tone="error",title="Keine CSV-Datei gewählt",copy="Bitte zuerst eine CSV-Datei auswählen."));return()}
    safe({selection<-.data_asset_activity_selection(activity_editor,runtime$context);portfolio<-.data_asset_activity_resolve(selection,"portfolios",input$activity_portfolio);data_asset_activity_csv_inspect_v1(activity_csv_center,runtime$context,file$datapath[[1L]],portfolio$portfolio_id)},function(model){
      activity_csv_inspection(model);activity_csv_preview(NULL)
      if(model$status%in%c("ready_for_preview","already_imported"))return(activity_csv_run_preview(model))
      if(!identical(model$status,"mapping_required"))tryCatch(activity_csv_resume_offer(data_asset_activity_csv_resumable_v1(activity_csv_center,runtime$context)),error=function(error)NULL)
      state(switch(model$status,
        mapping_required=list(tone="warning",title="Zuordnung nötig",copy="Einige Asset- oder Kontonamen der Datei sind nicht eindeutig. Bitte unten zuordnen und „Zuordnung übernehmen“ wählen."),
        resumable=list(tone="warning",title="Unterbrochener Import",copy="Diese Datei wurde bereits bestätigt, aber nicht vollständig übernommen. Bitte unter „Unterbrochenen Import fortsetzen“ abschließen."),
        list(tone="warning",title="Unterbrochener Import dieser Serie",copy="Für diese Exportserie ist ein anderer Import unterbrochen. Bitte ihn zuerst fortsetzen.")))
    })
  })
  activity_csv_resume_offer<-function(model){activity_csv_resumable(model);choices<-if(!length(model$candidates))c("Keine unterbrochenen Pläne"="")else c("Bitte wählen"="",stats::setNames(vapply(model$candidates,`[[`,character(1L),"resume_ref"),vapply(model$candidates,function(item)paste(item$import_key,"·",item$row_count,"Zeilen ·",item$previewed_at_utc),character(1L))));shiny::updateSelectInput(session,"activity_csv_resume_ref",choices=choices,selected="")}
  shiny::observeEvent(input$activity_csv_resume_refresh,safe(data_asset_activity_csv_resumable_v1(activity_csv_center,runtime$context),function(model){activity_csv_resume_offer(model);state(list(tone=if(length(model$candidates))"warning"else"neutral",title="Unterbrochene CSV-Pläne gelesen",copy=paste(length(model$candidates),"exakt resumierbare Pläne.")))}))
  shiny::observeEvent(input$activity_csv_resume,{
    if(is.null(input$activity_csv_resume_ref)||!nzchar(input$activity_csv_resume_ref)){state(list(tone="error",title="CSV-Fortsetzung blockiert",copy=pl_error_text_v1("data_asset_activity_csv_preview_required")));return()}
    safe(data_asset_activity_csv_resume_v1(activity_csv_center,runtime$context,input$activity_csv_resume_ref),function(result){invisible(refresh_activity_catalog());materialized<-update_realized_state("incremental");activity_csv_resumable(data_asset_activity_csv_resumable_v1(activity_csv_center,runtime$context));state(list(tone=if(is.null(materialized))"warning"else"neutral",title="Buchungs-CSV fortgesetzt",copy=paste(result$row_count,"Zeilen vollständig · Cash/Kursanbieter 0 · FIFO-Stand",if(is.null(materialized))"veraltet"else"aktualisiert")))} )
  })
  shiny::observeEvent(input$activity_csv_prepare,{
    model<-activity_csv_inspection();if(is.null(model)){state(list(tone="error",title="CSV-Vorschau nicht möglich",copy="Bitte zuerst „Datei prüfen“ wählen."));return()}
    activity_csv_run_preview(model,activity_csv_mapping_values(model))
  })
  # Buchen einer geprueften CSV-Vorschau; auch die Wertpapier-Belege (#446) buchen hierueber.
  activity_csv_execute_run<-function(after=NULL)safe({issued<-now_utc();data_asset_activity_csv_execute_v1(activity_csv_center,runtime$context,TRUE,issued,add_seconds(issued,600L))},function(result){activity_csv_preview(NULL);activity_csv_inspection(NULL);invisible(refresh_activity_catalog());invisible(refresh_activity_corrections());materialized<-update_realized_state("incremental");state(if(identical(result$status,"references_recorded"))data_asset_activity_csv_reference_state_v1(result)else list(tone=if(is.null(materialized))"warning"else"positive",title="CSV-Zeilen übernommen",copy=paste(result$created_event_count,"neue Buchung(en) gespeichert",if(result$already_committed_event_count>0)paste("·",result$already_committed_event_count,"aus einem unterbrochenen Lauf")else"",data_asset_activity_csv_reference_note_v1(result),"· FIFO-Stand",if(is.null(materialized))"noch nicht aktualisiert"else"aktualisiert")))
    if(is.function(after))after(result)})
  shiny::observeEvent(input$activity_csv_execute,{
    preview<-activity_csv_preview();if(is.null(preview)||!identical(preview$status,"ready_for_confirmation")){state(list(tone="error",title="Nichts zu übernehmen",copy="Es liegt keine übernahmebereite Vorschau vor. (Code: data_asset_activity_csv_preview_required)"));return()}
    activity_csv_execute_run()
  })
  activity_csv_download<-function(scope)shiny::downloadHandler(
    filename=function(){asset<-tryCatch(.data_asset_activity_resolve(.data_asset_activity_selection(activity_editor,runtime$context),"assets",input$activity_asset),error=function(error)NULL);slug<-if(identical(scope,"asset")&&!is.null(asset))tolower(gsub("[^A-Za-z0-9]+","-",asset$label))else"alle-assets";paste0("portelyra-buchungen-",substr(gsub("^-|-$","",slug),1L,40L),"-",format(Sys.Date(),"%Y-%m-%d"),".csv")},
    content=function(file){
      value<-tryCatch({selection<-.data_asset_activity_selection(activity_editor,runtime$context);portfolio_ref<-input$activity_portfolio;if((!is.character(portfolio_ref)||!nzchar(portfolio_ref))&&length(selection$portfolios$by_ref)==1L)portfolio_ref<-names(selection$portfolios$by_ref)[[1L]];portfolio<-.data_asset_activity_resolve(selection,"portfolios",portfolio_ref);asset<-if(identical(scope,"asset")).data_asset_activity_resolve(selection,"assets",input$activity_asset)else NULL
        data_asset_activity_csv_export_v1(activity_csv_center,runtime$context,portfolio$portfolio_id,if(is.null(asset))NULL else asset$asset_id,now_utc())},error=function(error)NULL)
      if(is.null(value)){state(list(tone="error",title="Export nicht möglich",copy=if(identical(scope,"asset"))"Bitte im Formular Portfolio und Asset wählen."else"Bitte im Formular ein Portfolio wählen."));stop("data_asset_activity_csv_export_failed",call.=FALSE)}
      writeBin(charToRaw(enc2utf8(value$content)),file)
      state(list(tone="neutral",title="CSV exportiert",copy=paste(value$row_count,"Buchung(en) exportiert",if(value$skipped_row_count>0)paste("·",value$skipped_row_count,"mit archivierten Stammdaten nicht enthalten")else"")))},
    contentType="text/csv")
  output$activity_csv_export_asset<-activity_csv_download("asset")
  output$activity_csv_export_all<-activity_csv_download("all")
  shiny::observeEvent(input$cash_refresh, safe(refresh_cash_catalog(), function(value) {
    state(list(tone="neutral",title="Cash-Abdeckung bereit",copy="Lesemodell nur mit Beschriftungen und browserlokale Auswahlverweise wurden gelesen; noch kein Schreiben."))
  }))
  shiny::observeEvent(list(
    input$cash_action,input$cash_portfolio,input$cash_account,input$cash_asset,input$cash_related_account,
    input$cash_coverage_mode,input$cash_effective_from,input$cash_effective_to,input$cash_event_type,
    input$cash_local_date,input$cash_local_time,input$cash_time_zone,input$cash_effective_utc,input$cash_amount,input$cash_flow_classification,
    input$cash_interest_amount,input$cash_linked_event,input$cash_as_of_date,input$cash_observed_balance,
    input$cash_evidence_fingerprint,input$cash_predecessors
  ),{
    if(!is.null(cash_preview())){cash_preview(NULL);shiny::updateCheckboxInput(session,"cash_confirm",value=FALSE);state(list(tone="warning",title="Vorschau der Cash-Abdeckung verworfen",copy="Formularwerte wurden geändert. Eine neue Vorschau ist erforderlich."))}
  },ignoreInit=TRUE)
  shiny::observeEvent(input$cash_prepare,safe(
    data_cash_coverage_editor_prepare_v1(cash_editor,runtime$context,cash_form(),now_utc()),
    function(preview){cash_preview(preview);shiny::updateCheckboxInput(session,"cash_confirm",value=FALSE);projection<-preview$projection;state(list(tone="warning",title="Vorschau der Cash-Abdeckung bereit",copy=paste("Abdeckung:",projection$period_count,"· Cash-Ereignisse:",projection$cash_event_count,"· Erträge:",projection$income_event_count,"· keine automatische Kopplung.")))}
  ))
  shiny::observeEvent(input$cash_execute,{
    preview<-cash_preview();if(is.null(preview)||!isTRUE(input$cash_confirm)){state(list(tone="error",title="Cash-Abdeckung blockiert",copy=pl_error_text_v1("data_cash_coverage_editor_confirmation_required")));return()}
    safe({data_cash_coverage_editor_confirm_v1(cash_editor,runtime$context,preview$preview_ref,now_utc());data_cash_coverage_editor_execute_v1(cash_editor,runtime$context,preview$preview_ref,now_utc())},function(result){cash_preview(NULL);shiny::updateCheckboxInput(session,"cash_confirm",value=FALSE);readiness_model(tryCatch(realized_adapter$readiness(runtime$context),error=function(error)NULL));state(list(tone="neutral",title="Cash-Abdeckung abgeschlossen",copy=paste(result$period_count,"Zeiträume ·",result$cash_event_count,"Cash-Ereignisse ·",result$income_event_count,"Ertragsfakten · Fassungen",result$revision_count,"· Stammdaten unverändert.")));invisible(refresh_cash_catalog())})
  })
  # --- Cash einfach buchen und Saldo pruefen (#417, #419) ------------------
  cash_simple_preview <- shiny::reactiveVal(NULL)
  cash_simple_notice <- shiny::reactiveVal(NULL)
  cash_check_preview <- shiny::reactiveVal(NULL)
  cash_check_notice <- shiny::reactiveVal(NULL)
  cash_failed <- function(notice, title) function(error) {
    notice(list(tone="error",title=title,copy=pl_error_text_v1(if(is.null(error$code))conditionMessage(error)else error$code)));NULL
  }
  cash_after_write <- function() {
    readiness_model(tryCatch(realized_adapter$readiness(runtime$context),error=function(error)NULL))
    invisible(tryCatch(refresh_cash_catalog(),error=function(error)NULL))
  }
  cash_date_missing <- function(value) !inherits(value,"Date")||length(value)!=1L||is.na(value)
  # Eine geaenderte Eingabe entwertet Vorschau und Haekchen: Bestaetigt wird, was
  # gezeigt wurde, nicht was inzwischen im Formular steht.
  shiny::observeEvent(list(input$cash_simple_account,input$cash_simple_date,input$cash_simple_kind,input$cash_simple_amount),{
    if(!is.null(cash_simple_preview())){cash_simple_preview(NULL);shiny::updateCheckboxInput(session,"cash_simple_confirm",value=FALSE)}
  },ignoreInit=TRUE)
  shiny::observeEvent(input$cash_simple_prepare,{
    shiny::updateCheckboxInput(session,"cash_simple_confirm",value=FALSE);cash_simple_preview(NULL);cash_simple_notice(NULL)
    betrag<-desktop_product_manual_decimal_v1(input$cash_simple_amount)
    fehlt<-c(if(!is.character(input$cash_simple_account)||!nzchar(input$cash_simple_account))"Konto",
             if(cash_date_missing(input$cash_simple_date))"Datum",if(!is.character(betrag)||!nzchar(betrag))"Betrag")
    if(length(fehlt)){cash_simple_notice(list(tone="warning",title="Angaben fehlen",copy=paste("Noch offen:",paste(fehlt,collapse=", "))));return()}
    cash_simple_preview(tryCatch(data_cash_coverage_editor_prepare_booking_v1(cash_editor,runtime$context,list(
      account_ref=input$cash_simple_account,cash_asset_ref="",local_date=input$cash_simple_date,
      kind=input$cash_simple_kind,amount_decimal=betrag),now_utc()),error=cash_failed(cash_simple_notice,"Cash-Buchung blockiert")))
  })
  # Kleinstbestaende auf geschlossenen Konten (#534): Saldo und Zustand aus dem juengsten Snapshot, Schliesstag aus der Ablage,
  # letzter Abgleich aus der Cash-Sicht; gebucht wird ueber das Formular „Cash-Buchung eintragen“.
  small_holdings_area <- data_small_holdings_server_v1(input, output, session,
    read = function() {
      if (is.null(portfolio_history_service) || is.null(statement_archive_service)) stop("data_small_holdings_unavailable")
      library <- portfolio_history_service$published()
      snapshot <- if (length(library$snapshots)) portfolio_history_service$show(library$snapshots[[1L]]$snapshot_id) else NULL
      states <- statement_archive_service$account_states()
      catalog <- asset_center_catalog()
      if (is.null(catalog)) { invisible(tryCatch(asset_center_autoload(reuse = TRUE), error = function(error) NULL)); catalog <- asset_center_catalog() }
      accounts <- if (is.list(catalog)) catalog$accounts else list()
      closed <- list()
      for (account in accounts) {
        id <- tryCatch(desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "account", account$ref), error = function(error) NULL)
        day <- if (is.character(id) && is.list(states[[id]])) states[[id]]$closed_on else NULL
        if (is.character(day) && length(day) == 1L) closed[[as.character(account$display_name)]] <- day
      }
      view <- cash_read_view(); if (is.null(view)) view <- tryCatch(data_cash_coverage_editor_read_view_v1(cash_editor, runtime$context), error = function(error) NULL)
      limit <- tryCatch(user_settings_service$read()$settings$small_holdings_threshold, error = function(error) NULL)
      list(snapshot = snapshot, closed_on = closed, periods = if (is.list(view)) view$periods else list(), threshold = if (is.character(limit)) limit else "1",
           events = if (is.list(view) && is.list(view$cash_history)) view$cash_history else list())
    },
    prefill = function(row) {
      model <- cash_catalog(); if (is.null(model)) { invisible(tryCatch(refresh_cash_catalog(), error = function(error) NULL)); model <- cash_catalog() }
      hit <- Filter(function(account) identical(account$label, row$account_label) || identical(account$selection_label, row$account_label), if (is.list(model)) model$accounts else list())
      if (length(hit) != 1L) return(FALSE)
      if (!isTRUE(row$booked)) {
        shiny::updateSelectInput(session, "cash_simple_account", selected = hit[[1L]]$ref)
        shiny::updateDateInput(session, "cash_simple_date", value = row$day)
        shiny::updateSelectInput(session, "cash_simple_kind", selected = row$kind)
        shiny::updateTextInput(session, "cash_simple_amount", value = sub(".", ",", row$amount_decimal, fixed = TRUE))
      }
      # Abgestimmtes Konto (#538): erst der Abgleich auf 0 am Tag der Ausbuchung nimmt den Rest aus dem Snapshot.
      if (isTRUE(row$reconciled)) {
        shiny::updateSelectInput(session, "cash_check_account", selected = hit[[1L]]$ref)
        shiny::updateDateInput(session, "cash_check_date", value = row$day)
        shiny::updateRadioButtons(session, "cash_check_evidence", selected = "owner_sighted")
        shiny::updateTextInput(session, "cash_check_balance", value = "0,00")
      }
      TRUE
    })
  shiny::observeEvent(input$cash_simple_execute,{
    preview<-cash_simple_preview()
    if(is.null(preview)||is.null(preview$preview_ref)||!isTRUE(input$cash_simple_confirm)){
      cash_simple_notice(list(tone="warning",title="Bestätigung fehlt",copy="Zuerst die Buchung prüfen und die Vorschau ausdrücklich bestätigen."));return()}
    result<-tryCatch({data_cash_coverage_editor_confirm_booking_v1(cash_editor,runtime$context,preview$preview_ref,now_utc())
      data_cash_coverage_editor_execute_booking_v1(cash_editor,runtime$context,preview$preview_ref,now_utc())},
      error=cash_failed(cash_simple_notice,"Cash-Buchung blockiert"))
    shiny::updateCheckboxInput(session,"cash_simple_confirm",value=FALSE);cash_simple_preview(NULL)
    if(is.null(result))return()
    shiny::updateTextInput(session,"cash_simple_amount",value="")
    cash_simple_notice(list(tone="positive",title=if(identical(result$status,"already_committed"))"Diese Buchung lag bereits vor" else "Cash-Buchung gespeichert",
      copy=paste(preview$command_count,if(identical(as.integer(preview$command_count),1L))"Fakt"else"Fakten","geschrieben · Konto und Datum bleiben für die nächste Buchung stehen.")))
    cash_after_write()
  })
  shiny::observeEvent(list(input$cash_check_account,input$cash_check_date,input$cash_check_evidence,input$cash_check_balance,input$cash_evidence_file),{
    if(!is.null(cash_check_preview())){cash_check_preview(NULL);shiny::updateCheckboxInput(session,"cash_check_confirm",value=FALSE)}
  },ignoreInit=TRUE)
  shiny::observeEvent(input$cash_check_prepare,{
    shiny::updateCheckboxInput(session,"cash_check_confirm",value=FALSE);cash_check_preview(NULL);cash_check_notice(NULL)
    art<-input$cash_check_evidence;saldo<-desktop_product_manual_decimal_v1(input$cash_check_balance)
    datei<-input$cash_evidence_file
    fehlt<-c(if(!is.character(input$cash_check_account)||!nzchar(input$cash_check_account))"Konto",
             if(cash_date_missing(input$cash_check_date))"Stand am",
             if(!identical(art,"owner_asserted_without_balance")&&(!is.character(saldo)||!nzchar(saldo)))"Saldo",
             if(identical(art,"document")&&(is.null(datei)||!is.data.frame(datei)||nrow(datei)!=1L))"Beleg-Datei")
    if(length(fehlt)){cash_check_notice(list(tone="warning",title="Angaben fehlen",copy=paste("Noch offen:",paste(fehlt,collapse=", "))));return()}
    cash_check_preview(tryCatch(data_cash_coverage_editor_prepare_check_balance_v1(cash_editor,runtime$context,list(
      account_ref=input$cash_check_account,cash_asset_ref="",as_of_date=input$cash_check_date,
      observed_balance_decimal=saldo,evidence_kind=art,
      # Gelesen wird die Datei nur fuer ihren Abdruck; gespeichert wird sie nicht.
      evidence_fingerprint=if(identical(art,"document"))data_cash_coverage_evidence_file_fingerprint_v1(datei$datapath[[1L]])else ""),now_utc()),
      error=cash_failed(cash_check_notice,"Abstimmung blockiert")))
  })
  shiny::observeEvent(input$cash_check_execute,{
    preview<-cash_check_preview()
    if(is.null(preview)||is.null(preview$preview_ref)||!isTRUE(input$cash_check_confirm)){
      cash_check_notice(list(tone="warning",title="Bestätigung fehlt",copy="Zuerst den Saldo prüfen und die Vorschau ausdrücklich bestätigen."));return()}
    result<-tryCatch({data_cash_coverage_editor_confirm_v1(cash_editor,runtime$context,preview$preview_ref,now_utc())
      data_cash_coverage_editor_execute_v1(cash_editor,runtime$context,preview$preview_ref,now_utc())},
      error=cash_failed(cash_check_notice,"Abstimmung blockiert"))
    shiny::updateCheckboxInput(session,"cash_check_confirm",value=FALSE);cash_check_preview(NULL)
    if(is.null(result))return()
    shiny::updateTextInput(session,"cash_check_balance",value="")
    angehoben<-identical(preview$explanation$operation,"raise_partial_to_reconciled")
    cash_check_notice(list(tone="positive",title=if(angehoben)"Abdeckung ist jetzt abgestimmt" else "Abstimmung festgehalten",
      copy=paste0("Stand ",.data_cash_coverage_datum(preview$explanation$as_of_date)," · Saldo ",.data_cash_coverage_betrag(preview$explanation$observed_balance_decimal),
        if(angehoben)" · der bisherige Zeitraum bleibt als ersetzter Stand erhalten." else ".")))
    cash_after_write()
  })
  # Die Nachweisuebersicht wird erst gelesen, wenn sie zu sehen ist, und folgt
  # jedem neu gelesenen Cash-Stand. Beim Sitzungsstart kostet sie nichts.
  cash_evidence_value <- shiny::reactive({
    cash_read_view()
    tryCatch(data_cash_coverage_editor_evidence_overview_v1(cash_editor,runtime$context,format(Sys.Date(),"%Y-%m-%d")),error=function(error)NULL)
  })
  shiny::observeEvent(input$cash_recovery_candidate,{
    if(!is.null(cash_recovery_preview())){cash_recovery_preview(NULL);shiny::updateCheckboxInput(session,"cash_recovery_confirm",value=FALSE)}
  },ignoreInit=TRUE)
  shiny::observeEvent(input$cash_recovery_prepare,{
    if(is.null(input$cash_recovery_candidate)||!nzchar(input$cash_recovery_candidate)){state(list(tone="error",title="Wiederaufnahme der Cash-Abdeckung blockiert",copy=pl_error_text_v1("data_cash_coverage_editor_recovery_required")));return()}
    safe(data_cash_coverage_editor_prepare_recovery_v1(cash_editor,runtime$context,input$cash_recovery_candidate,now_utc()),function(preview){cash_recovery_preview(preview);shiny::updateCheckboxInput(session,"cash_recovery_confirm",value=FALSE);state(list(tone="warning",title="Vorschau der Wiederaufnahme bereit",copy="Originalversuch wurde exakt reconciled; automatische Wiederholung bleibt ausgeschlossen."))})
  })
  shiny::observeEvent(input$cash_recovery_execute,{
    preview<-cash_recovery_preview();if(is.null(preview)||!isTRUE(input$cash_recovery_confirm)){state(list(tone="error",title="Wiederaufnahme der Cash-Abdeckung blockiert",copy=pl_error_text_v1("data_cash_coverage_editor_confirmation_required")));return()}
    safe({data_cash_coverage_editor_confirm_recovery_v1(cash_editor,runtime$context,preview$preview_ref,now_utc());data_cash_coverage_editor_execute_recovery_v1(cash_editor,runtime$context,preview$preview_ref,now_utc())},function(result){cash_recovery_preview(NULL);shiny::updateCheckboxInput(session,"cash_recovery_confirm",value=FALSE);state(list(tone="neutral",title="Cash-Wiederaufnahme abgeschlossen",copy=paste("Status:",result$status,"· Schema",result$schema_version,"· Stammdaten unverändert.")));invisible(refresh_cash_catalog())})
  })
  shiny::observeEvent(input$transaction_refresh, safe(refresh_transaction_catalog(), function(value) {
    state(list(tone = "neutral", title = "Transaktionsauswahl bereit", copy = "Nur browserlokale Auswahl-Referenzen wurden veröffentlicht."))
  }))
  shiny::observeEvent(input$transaction_load, {
    if (!nzchar(input$transaction_current)) return()
    safe(data_transaction_editor_prefill_v1(transaction_editor, runtime$context, input$transaction_current), function(form) {
      fields <- c(action = "transaction_action", profile = "transaction_profile", portfolio_ref = "transaction_portfolio", transaction_ref = "transaction_current",
                  effective_at_utc = "transaction_effective", local_date = "transaction_date", account_ref = "transaction_account", asset_ref = "transaction_asset",
                  cash_account_ref = "transaction_cash_account", cash_asset_ref = "transaction_cash_asset", counterparty_account_ref = "transaction_counterparty",
                  destination_account_ref = "transaction_destination", quantity_decimal = "transaction_quantity", unit_price_decimal = "transaction_price",
                  amount_decimal = "transaction_amount", fee_decimal = "transaction_fee", tax_decimal = "transaction_tax", memo = "transaction_memo")
      for (name in names(fields)) {
        if (fields[[name]] %in% c("transaction_action", "transaction_profile", "transaction_portfolio", "transaction_current", "transaction_account", "transaction_asset", "transaction_cash_account", "transaction_cash_asset", "transaction_counterparty", "transaction_destination")) shiny::updateSelectInput(session, fields[[name]], selected = form[[name]]) else shiny::updateTextInput(session, fields[[name]], value = form[[name]])
      }
      state(list(tone = "neutral", title = "Korrekturwerte geladen", copy = "Noch wurde nichts geschrieben."))
    })
  })
  shiny::observeEvent(input$transaction_prepare, safe(data_transaction_editor_prepare_v1(transaction_editor, runtime$context, transaction_form(), now_utc()), function(preview) {
    settlement_label <- switch(
      preview$settlement_mode,
      derived_exact = "Cash exakt abgeleitet",
      explicit_cash = "belegtes Cash separat",
      not_applicable = "nicht anwendbar",
      preview$settlement_mode
    )
    transaction_preview(preview); state(list(
      tone = "warning", title = "Transaktionsvorschau bereit",
      copy = paste(length(preview$postings), "Buchungszeilen · Abrechnung:", settlement_label, "· warten auf Einmalbestätigung.")
    ))
  }))
  shiny::observeEvent(input$transaction_execute, {
    preview <- transaction_preview()
    if (is.null(preview) || !isTRUE(input$transaction_confirm)) {
      state(list(tone = "error", title = "Transaktion blockiert", copy = pl_error_text_v1("data_transaction_editor_confirmation_required"))); return()
    }
    safe(data_transaction_editor_execute_v1(transaction_editor, runtime$context, preview$preview_ref, TRUE, now_utc()), function(result) {
      transaction_preview(NULL); shiny::updateCheckboxInput(session, "transaction_confirm", value = FALSE)
      state(list(tone = "neutral", title = "Transaktion abgeschlossen", copy = paste(result$posting_count, "Buchungszeilen bestätigt (nur fortgeschrieben).")))
      invisible(read_workspace()); invisible(refresh_transaction_catalog())
    })
  })
  shiny::observeEvent(input$catalog_refresh, safe(refresh_catalog_model(), function(value) {
    state(list(tone = "neutral", title = "Stammdaten-Auswahl bereit", copy = "Nur browserlokale Auswahl- und Exchange-Referenzen wurden veröffentlicht."))
  }))
  shiny::observeEvent(list(input$catalog_entity_type, catalog_model()), {
    model <- catalog_model(); if (is.null(model)) return()
    rows <- Filter(function(row) !identical(row$status, "archived"), model[[paste0(input$catalog_entity_type, "s")]])
    choices <- if (!length(rows)) c("Bitte wählen" = "") else c("Bitte wählen" = "", stats::setNames(
      vapply(rows, `[[`, character(1L), "ref"), vapply(rows, `[[`, character(1L), "display_name")
    ))
    shiny::updateSelectInput(session, "catalog_entity_ref", choices = choices, selected = "")
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$catalog_prepare, safe(
    desktop_catalog_editor_prepare_v1(catalog_editor, runtime$context, catalog_form(), now_utc()),
    function(preview) {
      catalog_preview(preview); shiny::updateCheckboxInput(session, "catalog_confirm", value = FALSE)
      state(list(tone = "warning", title = "Archivierung geprüft", copy = paste(preview$display_name, "wartet auf Einmalbestätigung.")))
    }
  ))
  shiny::observeEvent(input$catalog_execute, {
    preview <- catalog_preview()
    if (is.null(preview) || !isTRUE(input$catalog_confirm)) {
      state(list(tone = "error", title = "Stammdaten-Vorgang blockiert", copy = pl_error_text_v1("desktop_catalog_confirmation_required"))); return()
    }
    safe(desktop_catalog_editor_execute_v1(catalog_editor, runtime$context, preview, TRUE), function(result) {
      catalog_preview(NULL); shiny::updateCheckboxInput(session, "catalog_confirm", value = FALSE)
      invisible(read_workspace()); invisible(refresh_catalog_model()); invisible(refresh_transaction_catalog())
      invisible(tryCatch(cash_import_load(), error = function(error) NULL))
      state(list(tone = "neutral", title = "Stammdaten-Vorgang abgeschlossen", copy = paste(result$entity_type, result$action, "wurde auditiert (nur fortgeschrieben).")))
    })
  })
  shiny::observeEvent(input$catalog_csv_prepare, {
    file <- input$catalog_csv_file
    if (is.null(file) || nrow(file) != 1L || !identical(file$name[[1L]], "desktop-catalog.csv")) {
      state(list(tone = "error", title = "CSV-Vorschau blockiert", copy = pl_error_text_v1("desktop_csv_source_invalid"))); return()
    }
    safe(spotcore::desktop_csv_import_prepare_v1(catalog_csv_center, runtime$context, file$datapath[[1L]], now_utc()), function(preview) {
      catalog_csv_preview(preview); shiny::updateCheckboxInput(session, "catalog_csv_confirm", value = FALSE)
      state(list(tone = "warning", title = "CSV-Plan bereit", copy = paste(preview$counts$pending_row_count, "explizite Create-Zeilen warten auf Einmalbestätigung.")))
    })
  })
  shiny::observeEvent(input$catalog_csv_resume, safe(
    spotcore::desktop_csv_import_restart_preview_v1(catalog_csv_center, runtime$context),
    function(preview) {
      catalog_csv_preview(preview); shiny::updateCheckboxInput(session, "catalog_csv_confirm", value = FALSE)
      state(list(tone = "warning", title = "CSV-Fortsetzung bereit", copy = paste(preview$counts$completed_row_count, "Zeilen sind bereits exakt bestätigt.")))
    }
  ))
  shiny::observeEvent(input$catalog_csv_execute, {
    preview <- catalog_csv_preview()
    if (is.null(preview) || !isTRUE(input$catalog_csv_confirm)) {
      state(list(tone = "error", title = "CSV-Plan blockiert", copy = pl_error_text_v1("desktop_csv_confirmation_required"))); return()
    }
    safe(spotcore::desktop_csv_import_execute_v1(catalog_csv_center, runtime$context, preview, TRUE, now_utc()), function(result) {
      catalog_csv_preview(NULL); shiny::updateCheckboxInput(session, "catalog_csv_confirm", value = FALSE)
      invisible(read_workspace()); invisible(refresh_catalog_model()); invisible(refresh_transaction_catalog())
      state(list(tone = "neutral", title = "CSV-Plan abgeschlossen", copy = "Alle Zeilen zum Neuanlegen wurden über auditierte Vorgänge ausgeführt."))
    })
  })
  # Der Cutoff ist die Tagesgrenze nach dem Bewertungsdatum. Ihn von Hand zu
  # tippen war eine Fehlerquelle ohne Nutzen.
  shiny::observeEvent(input$run_as_of_date, {
    day <- input$run_as_of_date
    if (!inherits(day, "Date") || length(day) != 1L || is.na(day)) return(invisible(NULL))
    # Hoechstens jetzt: zwischen Mitternacht und 2 Uhr Ortszeit laege die Tagesgrenze nach dem Bewertungsdatum (UTC) noch vorn,
    # und der FIFO-Lauf wiese sie ab.
    cutoff <- format(day + 1L, "%Y-%m-%dT00:00:00Z")
    shiny::updateTextInput(session, "run_cutoff", value = if (cutoff > now_utc()) now_utc() else cutoff)
  })
  # Manuelle Evidenz je Asset (#422): Die Suche bietet die aktiven Nicht-Cash-Assets; ein gewaehltes bleibt nach dem Neulesen gewaehlt.
  shiny::observeEvent(run_catalog(), {
    assets <- run_evidence_assets()
    choices <- stats::setNames(vapply(assets, function(asset) as.character(asset$ref), character(1L)),
      vapply(assets, function(asset) paste0(asset$label, " · ", asset$asset_type), character(1L)))
    keep <- shiny::isolate(input$run_evidence_asset)
    shiny::updateSelectizeInput(session, "run_evidence_asset", choices = c("Asset suchen …" = "", choices),
      selected = if (is.character(keep) && length(keep) == 1L && keep %in% choices) keep else "")
    # Gespeicherte Werte von Assets, die nicht mehr aktiv sind, zaehlen nicht mehr.
    run_evidence_store(run_evidence_store()[intersect(names(run_evidence_store()), unname(choices))])
  }, ignoreNULL = TRUE)
  # Beim Wechsel bleiben die Werte des bisherigen Assets stehen; danach zeigen die Felder die des neuen.
  shiny::observeEvent(input$run_evidence_asset, {
    assets <- run_evidence_assets()
    by_ref <- stats::setNames(assets, vapply(assets, function(asset) as.character(asset$ref), character(1L)))
    previous <- run_evidence_current()
    if (is.character(previous) && length(previous) == 1L && !is.null(by_ref[[previous]]))
      run_evidence_store(desktop_run_evidence_store_v1(run_evidence_store(), by_ref[[previous]], run_evidence_live()))
    selected <- input$run_evidence_asset
    if (!is.character(selected) || length(selected) != 1L || is.null(by_ref[[selected]])) { run_evidence_current(NULL); return() }
    run_evidence_show(by_ref[[selected]])
    run_evidence_current(selected)
  }, ignoreNULL = FALSE, ignoreInit = TRUE)
  shiny::observeEvent(input$run_evidence_reset, {
    selected <- run_evidence_current(); assets <- run_evidence_assets()
    asset <- Filter(function(item) identical(as.character(item$ref), selected), assets)
    if (!length(asset)) return()
    store <- run_evidence_store(); store[[selected]] <- NULL; run_evidence_store(store)
    run_evidence_show(asset[[1L]])
  })
  shiny::observeEvent(input$run_catalog_refresh, action_feedback$run('run', safe(refresh_run_catalog(), function(value) {
    state(list(tone = "neutral", title = "Abschluss-Eingaben bereit", copy = "Noch wurde kein Rechenlauf gestartet."))
  })))
  shiny::observeEvent(input$run_valuation_read,safe(asset_center_valuation_service$read_completed(),function(value){
    run_valuations(value$completed)
    choices<-stats::setNames(vapply(value$completed,function(v)v$preview_ref,character(1L)),
      vapply(seq_along(value$completed),function(i){v<-value$completed[[i]];paste(i,v$start_date,v$end_date,v$status,v$freshness)},character(1L)))
    shiny::updateSelectInput(session,"run_valuation_ref",choices=choices)
    run_preview(NULL);shiny::updateCheckboxInput(session,"run_confirm",value=FALSE)
  }),ignoreInit=TRUE)
  shiny::observeEvent(list(input$run_completed_market,input$run_valuation_ref,input$run_portfolio,input$run_mode,
    input$run_as_of_date,input$run_cutoff,input$run_tax_mode,input$run_capital_rate,input$run_personal_rate,
    input$run_soli_rate,input$run_church_applicable,input$run_church_rate,
    input$run_fee_source,input$run_fee_fixed,input$run_fee_percentage,
    lapply(Filter(function(a)a$asset_type!="cash"&&a$status=="active",run_catalog()$assets),run_asset_form)),{
    run_preview(NULL);shiny::updateCheckboxInput(session,"run_confirm",value=FALSE)
  },priority=20)
  # Elf Felder, ein Fehlercode: desktop_run_center_input_invalid sagte nicht,
  # welches fehlt. Zweimal kostete das eine Runde - einmal das nicht gewaehlte
  # Portfolio, einmal eine veraltete Seite ohne die neue Gebuehrenauswahl. Die
  # Pruefung sitzt vor dem Vertrag und nennt das Feld; der Vertrag prueft
  # weiterhin selbst (Befunde 28./29.09.2026).
  # Seit 11.10.2026 prueft sie auch die Form: ein Dezimalkomma, angehaengte
  # Nullen, eine Kirchensteuer-Angabe ohne Modell v2 oder ein halb gefuelltes
  # Kursfeld einer Asset-Karte endeten im selben Sammelcode. Die Regeln stehen in
  # desktop_product_run_form_complaint_v1 (desktop_product_input_controls_v1.R).
  run_form_complaint <- function(form) desktop_product_run_form_complaint_v1(form,
    Filter(function(asset) asset$asset_type != "cash" && asset$status == "active", run_catalog()$assets))
  # Der Buchungsbestand ist aus den Stammdaten abgeleitet und traegt deren Stand
  # von der letzten Buchung. Aendert sich danach etwas an den Stammdaten - eine
  # Bewertungsart, ein neues Asset, eine Kurszuordnung -, passt beides nicht mehr
  # zusammen, und der Vertrag wies den Plan mit dem Sammelcode ab: Es
  # reichte eine Minute zwischen letzter Buchung und geaenderter
  # Bewertungsart. Der Bestand wird deshalb hier angeglichen, ohne
  # Buchung; abgewiesen wird nur noch, wenn das nicht gelingt - mit Grund.
  # Dieselbe Bindung braucht „Alles aktualisieren“ fuer den Abschluss (#463).
  run_semantic_binding <- function() {
    read_semantic_binding <- function() if (is.null(per_asset_product_adapter)) NULL else tryCatch(
      per_asset_product_adapter$product_binding(runtime$context), error=function(error) NULL)
    binding <- read_semantic_binding()
    aligned <- FALSE
    if (is.list(binding) && identical(binding$status, "available") && !identical(binding$canonical_fingerprint,
        digest::digest(file = spotcore::runtime_canonical_path(runtime$context), algo = "sha256", serialize = FALSE))) {
      outcome <- if (is.null(activity_republication_adapter)) simpleError("per_asset_review_adapter_failed") else
        tryCatch(activity_republication_adapter$republish(runtime$context, now_utc()), error=function(error) error)
      if (inherits(outcome, "error")) {
        return(list(status = "failed", copy = data_run_plan_alignment_failure_text_v1(
          tryCatch(spotcore::desktop_product_safe_error_code_v1(outcome), error=function(error) "desktop_product_boundary_failed"))))
      }
      aligned <- identical(outcome$status, "republished")
      binding <- read_semantic_binding()
      # Eine neue Generation: Die Zeilenschluessel der Buchungsliste und der
      # FIFO-Stand haengen an ihr, wie nach jeder Buchung.
      tryCatch(invisible(refresh_activity_catalog()), error=function(error) NULL)
      tryCatch(invisible(refresh_activity_corrections()), error=function(error) NULL)
      invisible(update_realized_state("incremental"))
    }
    list(status = "ready", aligned = aligned, binding = if (!is.list(binding) || !identical(binding$status, "available")) NULL else
      binding[c("status", "ledger_path", "ledger_fingerprint", "canonical_fingerprint", "semantic_contracts")])
  }
  shiny::observeEvent(input$run_prepare, action_feedback$run('run', {
    catalog <- run_catalog()
    if (is.null(catalog)) { state(list(tone = "error", title = "Abschlussplan blockiert", copy = pl_error_text_v1("desktop_run_center_catalog_unavailable"))); return() }
    assets <- Filter(function(asset) asset$asset_type != "cash" && asset$status == "active", catalog$assets)
    form <- list(
      portfolio_ref = input$run_portfolio, run_mode = input$run_mode, as_of_date = .data_tax_iso_date_v1(input$run_as_of_date), cutoff_at_utc = input$run_cutoff,
      tax_mode = input$run_tax_mode, capital_income_tax_rate = input$run_capital_rate, personal_income_tax_rate = input$run_personal_rate,
      solidarity_surcharge_rate = input$run_soli_rate, church_tax_applicable = input$run_church_applicable,
      church_tax_rate = input$run_church_rate,
      fee_source = input$run_fee_source,
      fee_fixed_decimal = if (identical(input$run_fee_source, "fixed_per_trade")) input$run_fee_fixed else NULL,
      fee_percentage_rate_decimal = if (identical(input$run_fee_source, "percentage_of_turnover")) input$run_fee_percentage else NULL,
      asset_inputs = lapply(assets, run_asset_form), grouping_mode = "none"
    )
    complaint <- run_form_complaint(form)
    if (!is.null(complaint)) {
      state(list(tone = "warning", title = "Eingabe unvollständig", copy = complaint)); return()
    }
    bound <- run_semantic_binding()
    if (identical(bound$status, "failed")) { state(list(tone = "error", title = "Abschlussplan blockiert", copy = bound$copy)); return() }
    aligned <- bound$aligned; semantic_binding <- bound$binding
    safe({
      market_binding<-NULL
      if(isTRUE(input$run_completed_market)) {
        matches<-Filter(function(v)identical(v$preview_ref,input$run_valuation_ref),run_valuations())
        if(length(matches)!=1L)stop("desktop_market_valuation_completion_required",call.=FALSE)
        market_binding<-asset_center_valuation_service$run_binding(matches[[1L]]$preview_ref,form$as_of_date)$binding
      }
      spotcore::desktop_run_center_prepare_v1(run_center, runtime$context, form, now_utc(), runtime$data_space_label, semantic_binding,market_binding)
    }, function(preview) {
      run_preview(preview); state(list(tone = "warning", title = "Abschlussplan bereit", copy = paste(c(
        paste(length(preview$stages), "Stufen warten auf Einmalbestätigung."),
        if (aligned) data_run_plan_alignment_notice_text_v1()), collapse = " ")))
    })
  }))
  shiny::observeEvent(input$run_execute, action_feedback$run('run', {
    preview <- run_preview()
    if (is.null(preview) || !isTRUE(input$run_confirm)) { state(list(tone = "error", title = "Abschluss blockiert", copy = pl_error_text_v1("desktop_run_center_confirmation_invalid"))); return() }
    safe({
      issued <- now_utc(); confirmation <- spotcore::desktop_run_center_build_confirmation_v1(run_center, runtime$context, preview, issued, add_seconds(issued, 300L),project_root)
      spotcore::desktop_run_center_execute_v1(run_center, runtime$context, preview, confirmation, issued, project_root)
    }, function(result) {
      shiny::updateCheckboxInput(session, "run_confirm", value = FALSE); run_preview(NULL)
      state(list(tone = if (result$status == "completed") "neutral" else "warning", title = paste("Abschluss", pl_run_status_label_v1(result$status)), copy = if (is.null(result$failure_code)) "Der neue Stand ist veröffentlicht." else pl_error_text_v1(result$failure_code)))
      load_published_workflow()
    })
  }))
  shiny::observeEvent(input$run_resume, action_feedback$run('run', safe(spotcore::desktop_run_center_resume_v1(runtime$context, project_root), function(result) {
    state(list(tone = if (result$status == "completed") "neutral" else "warning", title = paste("Abschluss", pl_run_status_label_v1(result$status)), copy = if (is.null(result$failure_code)) "Der bestätigte Abschluss wurde sicher fortgesetzt." else pl_error_text_v1(result$failure_code)))
    load_published_workflow()
  })))
  shiny::observeEvent(input$run_result_refresh, load_published_workflow(), ignoreInit = TRUE)
  # Der veroeffentlichte Stand wird gelesen, wenn seine Anzeige gebraucht wird, nicht
  # beim Aufbau jeder Sitzung. Er steht im zugeklappten Run Center unter "4. Steuer" (bis rc.297 im Reiter "Abschluss"); beim Start
  # kostete das Lesen mehrere Sekunden, bevor die Sitzung ueberhaupt antworten konnte.

  output$statement_guided_state<-shiny::renderUI({
    preview<-statement_exchange_preview();mapping<-statement_exchange_mapping();handoff<-statement_exchange_handoff();batch<-statement_reward_valuation_batch();result<-statement_guided_result();exchange<-statement_exchange_state()
    counts<-statement_guided_counts(batch)
    # Fortgesetzter Lauf ohne Datei (#520): steht gleich bei Pruefen und Buchen.
    resumed<-is.null(preview)&&!is.null(counts)&&!is.null(statement_batch_source())
    step<-1L;title<-"Datei und Zeitraum wählen";copy<-"Dann „Rewards anzeigen“. Die Vorschau schreibt nichts.";tone<-"neutral"
    if(!is.null(preview)){step<-2L;title<-"Zuordnung prüfen";copy<-paste(exchange$copy,"Asset und Konto kontrollieren, dann „Zuordnung prüfen“.");tone<-"neutral"}
    if(!is.null(mapping)){
      new<-statement_guided_new_count();booked<-length(statement_exchange_booked())
      step<-3L;title<-if(new>0L)sprintf("%d neue Rewards vorbereiten",new)else"Nichts Neues zu übernehmen"
      copy<-paste(c(sprintf("%d neu",new),if(booked>0L)sprintf("%d bereits gebucht",booked)),collapse=" · ");tone<-if(new>0L)"warning"else"positive"
    }
    if((!is.null(handoff)||resumed)&&!is.null(counts)){
      step<-4L;title<-if(counts$ready>0L)sprintf("%d Rewards buchen",counts$ready)else"Vorbereitet";copy<-"";tone<-"warning"
      # Erst wenn auch nichts Ungeprueftes mehr offen ist, ist das Statement durch.
      if(counts$ready==0L&&counts$pending==0L&&counts$blocked==0L&&counts$unvalidated==0L&&counts$total>0L){title<-"Auszug abgeschlossen";tone<-"positive"}
      if(counts$ready==0L&&counts$pending==0L&&counts$blocked==0L&&counts$unvalidated>0L){
        title<-sprintf("%d Rewards warten auf die Prüfung",counts$unvalidated)
        copy<-"Die Klärung hat die Prüfung zurückgesetzt. Erst prüfen, dann buchen."}
    }
    if(!is.null(result)){title<-result$title;copy<-result$copy;tone<-result$tone}
    if(!is.null(exchange)&&is.null(preview)&&!identical(exchange$tone,"neutral")){title<-exchange$title;copy<-if(identical(exchange$title,"Keine Datei gewählt"))exchange$copy else paste(exchange$copy,"Andere Datei, Börse oder anderen Zeitraum wählen.");tone<-if(exchange$tone%in%c("error","blocked"))"error"else"warning"}
    if(!is.null(exchange)&&exchange$tone%in%c("error","blocked")&&!is.null(preview)&&is.null(mapping)){title<-exchange$title;copy<-exchange$copy;tone<-"error"}
    panel_tone<-if(identical(tone,"success"))"positive"else tone
    shiny::tagList(shiny::div(class="pl-section-copy",shiny::strong(sprintf("Schritt %d von 4",step)),
      if(resumed)" · fortgesetzter Lauf aus früheren Läufen, ohne Datei: prüfen → buchen" else " · Datei → Zuordnung → Vorbereiten → Buchen"),
      portelyra_status_panel(title,copy,tone=panel_tone),data_statement_reward_error_code_ui_v1(result))
  })
  output$statement_guided_action<-shiny::renderUI({
    preview<-statement_exchange_preview();mapping<-statement_exchange_mapping();handoff<-statement_exchange_handoff();counts<-statement_guided_counts(statement_reward_valuation_batch())
    proxy<-function(target,label)shiny::tags$button(type="button",class="btn btn-primary action-button",onclick=paste0("var b=document.getElementById('",target,"');if(b){b.click();}return false;"),label)
    restart<-function(primary=FALSE)shiny::tags$button(type="button",id="statement_guided_restart_button",class=if(primary)"btn btn-primary"else"btn btn-default",
      onclick="var f=document.getElementById('statement_exchange_file');if(f){f.value='';var g=f.closest('.form-group');if(g){var t=g.querySelector('input[type=text]');if(t){t.value='';}var bar=g.querySelector('.progress');if(bar){bar.style.visibility='hidden';}}}Shiny.setInputValue('statement_guided_restart',Date.now(),{priority:'event'});return false;",
      "Neuen Auszug beginnen")
    finished<-!is.null(statement_guided_result())&&statement_guided_result()$tone%in%c("positive","error")
    # Ein fortgesetzter Lauf (#520) hat keine Datei: Bis rc.339 stand hier dann "Rewards anzeigen", und blockierte Entwuerfe
    # liessen sich ohne Expertenschalter nicht erneut pruefen.
    resumed<-is.null(preview)&&!is.null(counts)&&!is.null(statement_batch_source())
    if(!resumed){
      if(is.null(preview))return(proxy("statement_exchange_preview_run","Rewards anzeigen"))
      if(is.null(mapping))return(shiny::div(class="pl-editor-actions",proxy("statement_exchange_mapping_run","Zuordnung prüfen"),restart()))
      if(is.null(handoff)){
        new<-statement_guided_new_count();if(new==0L)return(restart(TRUE))
        return(shiny::div(class="pl-editor-actions",shiny::actionButton("statement_guided_prepare_run",sprintf("%d Rewards vorbereiten und prüfen",new),class="btn-primary"),shiny::span(class="pl-field-hint","Legt Entwürfe an und prüft sie. Noch keine Buchung.")))
      }
    }
    if(is.null(counts))return(restart(finished))
    partial<-if(counts$ready>0L)shiny::actionButton("statement_guided_book_run",sprintf("%d fertige Rewards buchen – %d bleiben offen",counts$ready,counts$pending+counts$blocked+counts$unvalidated),class="btn-default")else NULL
    if(counts$pending>0L)return(shiny::div(class="pl-editor-actions",shiny::actionButton("statement_guided_revalidate_run","Nach dem Ergänzen erneut prüfen",class="btn-default"),partial,restart()))
    # Blockiert, aber alle bewertet: erneut pruefen ist der naechste Schritt - ein Reward in der Sekunde einer gebuchten Buchung
    # wird dabei versetzt (rc.323); was danach blockiert bleibt, nennt "Blockierte Rewards" mit Grund (#520).
    if(counts$blocked>0L)return(shiny::div(class="pl-editor-actions",
      shiny::actionButton("statement_guided_revalidate_run",sprintf("%d Rewards erneut prüfen",counts$blocked+counts$unvalidated),class="btn-primary"),partial,
      shiny::span(class="pl-field-hint","Prüft blockierte und ungeprüfte Rewards erneut. Noch keine Buchung."),restart()))
    # Geprueft, aber noch nicht bereit: das entsteht, wenn eine Klaerung die
    # Pruefung zurueckgesetzt hat - etwa nach der Bestaetigung zeitgleicher
    # Rewards. Ohne diesen Fall bot die Karte nur "Neues Statement beginnen" an,
    # und geklaerte Rewards blieben unbuchbar (#422).
    if(counts$unvalidated>0L)return(shiny::div(class="pl-editor-actions",
      shiny::actionButton("statement_guided_revalidate_run",sprintf("%d Rewards prüfen",counts$unvalidated),class="btn-primary"),
      shiny::span(class="pl-field-hint","Prüft die geklärten Rewards erneut. Noch keine Buchung."),restart()))
    if(counts$ready>0L)return(shiny::div(class="pl-editor-actions",shiny::actionButton("statement_guided_book_run",sprintf("%d Rewards buchen",counts$ready),class="btn-primary"),shiny::span(class="pl-field-hint","Bucht genau diese Rewards. Rückgängig nur über „Buchung korrigieren“.")))
    restart(TRUE)
  })
  # Special cases appear only when needed: missing valuation, time collisions.
  output$statement_guided_special<-shiny::renderUI({
    counts<-statement_guided_counts(statement_reward_valuation_batch());if(is.null(counts))return(NULL)
    shiny::tagList(
      if(counts$pending>0L){
        preview<-statement_reward_market_batch_preview();catalog<-activity_catalog()
        label<-function(ref){if(is.null(catalog))return("Asset");hits<-Filter(function(row)identical(row$ref,ref),catalog$assets);if(length(hits))hits[[1L]]$label else"Asset"}
        missing<-data_statement_reward_missing_summary_v1(preview,statement_reward_valuation_batch(),label)
        ready<-if(is.list(preview))as.integer(preview$ready_count)else 0L
        # Von Hand bewerten laesst sich nur ein Reward ohne Wert im Statement. Traegt das Statement den Wert in Fremdwaehrung
        # (Kraken: USD), fehlt nur der Devisenkurs - dann boten Text und Aufklapper eine Eingabe an, die es nicht gibt (#520).
        open_pending<-Filter(function(row)identical(row$valuation_summary$lifecycle,"valuation_pending")&&!identical(row$status,"committed"),statement_reward_valuation_batch()$drafts)
        manual<-any(vapply(open_pending,function(row)!identical(row$valuation_summary$origin,"source_provided"),logical(1L)))
        shiny::div(class="pl-write-boundary",shiny::tags$h4("Kurs ergänzen"),
          shiny::p(class="pl-section-copy",sprintf("%d Rewards brauchen einen Wert in EUR. Werte aus dem Auszug bleiben geschützt; ergänzt wird nur, was fehlt.",counts$pending)),
          if(ready>0L)shiny::div(class="pl-editor-actions",shiny::actionButton("statement_guided_market_all_run",sprintf("Gespeicherte Kurse für %d Rewards übernehmen",ready),class="btn-primary"),shiny::span(class="pl-field-hint","Nutzt nur bereits gespeicherte Markt- und Devisenkurse; kein Abruf."))else NULL,
          if(length(missing))shiny::tagList(shiny::p(shiny::strong("Es fehlen gespeicherte Kurse:")),shiny::tags$ul(lapply(missing,shiny::tags$li)),
            shiny::p(class="pl-section-copy",if(manual)"Im Tab Marktdaten die Historien bzw. Devisenkurse bis zu diesen Tagen aktualisieren, danach hier „Nach dem Ergänzen erneut prüfen“. Oder den Wert je Reward manuell eintragen."
              else"Der Wert steht schon im Auszug, aber in Fremdwährung: Es fehlt nur der Devisenkurs. Im Reiter „Marktdaten“ die Devisenkurse bis zu diesen Tagen aktualisieren, danach hier „Nach dem Ergänzen erneut prüfen“."),
            shiny::tags$button(type="button",class="btn btn-default",onclick="var t=document.querySelector('#asset_center_step a[data-value=\"Marktdaten\"]');if(t){t.click();window.scrollTo({top:0,behavior:'smooth'});}return false;","Zum Tab Marktdaten"))else NULL,
          shiny::tags$details(class="pl-disclosure",open=if(ready==0L&&!length(missing))NA else NULL,shiny::tags$summary(if(manual)"Wert je Reward manuell eintragen"else"Bewertung je Reward ansehen"),shiny::uiOutput("statement_reward_valuation_editor")))
      }else NULL,
      # Blockiert heisst nicht zwingend zeitgleich: Es kann auch an der Mengenskala liegen, und hier stand trotzdem "haben denselben
      # Zeitpunkt". Der Grund laesst sich jetzt je Reward anzeigen (#420).
      if(counts$blocked>0L)shiny::div(class="pl-write-boundary",shiny::tags$h4("Blockierte Rewards"),
        shiny::p(class="pl-section-copy",sprintf("%d Rewards hat der Kern abgelehnt. Der Grund wird aus derselben Prüfung gelesen und ändert nichts; je Reward kann das einige Sekunden dauern.",counts$blocked)),
        shiny::div(class="pl-editor-actions",shiny::actionButton("statement_block_reasons_run","Gründe anzeigen",class="btn-default")),
        # Von Hand buchen (#520, Festlegung 28.10.2026): je blockiertem Reward Zeitpunkt, Asset, Menge, Wert und Konto.
        shiny::tags$details(class="pl-disclosure",shiny::tags$summary(sprintf("Die %d blockierten Rewards von Hand buchen",counts$blocked)),
          shiny::p(class="pl-section-copy","In „Manuell“ je Reward eine Buchung „Reward“ mit diesen Angaben erfassen. Liegt dort schon eine Buchung desselben Assets in derselben Sekunde, wird der Reward um Sekunden versetzt gebucht. Danach oben „Aus früheren Läufen offen“ → „Rest als von Hand gebucht stilllegen“."),
          # Ohne Kennung kaeme der Reward beim naechsten Import der ganzen Historie wieder als neu (#520).
          shiny::p(class="pl-section-copy",shiny::strong("Wichtig: "),"Die Kennung aus der Zeile des Auszugs ins Feld „Transaktions-ID“ eintragen – bei Kraken die txid, bei Coinbase die ID, bei Bison die Transaction ID. Daran erkennt der nächste Import die Buchung und bietet den Reward nicht erneut an. BSDEX hat keine Kennung: dort die Uhrzeit genau übernehmen; wird sie versetzt, beim nächsten BSDEX-Import diesen Reward nicht erneut buchen."),
          shiny::div(class="pl-table-wrap",shiny::tableOutput("statement_blocked_rewards"))),
        shiny::uiOutput("statement_block_reasons_state"),
        shiny::tags$h4("Zeitgleiche Rewards klären"),shiny::p(class="pl-section-copy","Der häufigste Grund: derselbe Zeitpunkt wie ein anderer Reward desselben Assets. Sind es fachlich verschiedene Zahlungen, die Reihenfolge aus dem Auszug bestätigen."),
        shiny::div(class="pl-editor-actions",shiny::tags$button(type="button",class="btn btn-default action-button",onclick="var b=document.getElementById('statement_reward_collision_prepare');if(b){b.click();}return false;","Zeitgleiche Rewards anzeigen")),
        shiny::uiOutput("statement_reward_collision_guided"))else NULL)
  })
  output$statement_blocked_rewards<-shiny::renderTable({
    batch<-statement_reward_valuation_batch();catalog<-activity_catalog()
    rows<-if(is.list(batch))Filter(function(row)identical(row$validation_status,"blocked")&&!identical(row$status,"committed"),batch$drafts)else list()
    if(!length(rows))return(NULL)
    label<-function(items,ref){hits<-if(is.list(items))Filter(function(item)identical(item$ref,ref),items)else list();if(length(hits))hits[[1L]]$label else "–"}
    text<-function(value)if(is.null(value)||length(value)!=1L||is.na(value))"" else as.character(value)
    german<-function(value)sub(".",",",text(value),fixed=TRUE)
    data.frame(
      Zeitpunkt=vapply(rows,function(row){day<-text(row$event_summary$local_date);paste(if(nzchar(day))format(as.Date(day),"%d.%m.%Y")else"–",text(row$event_summary$local_time))},character(1L)),
      Asset=vapply(rows,function(row)label(catalog$assets,row$asset_ref),character(1L)),
      Menge=vapply(rows,function(row)german(row$event_summary$quantity_decimal),character(1L)),
      Wert=vapply(rows,function(row){currency<-text(row$valuation_summary$price_currency);gross<-text(row$event_summary$gross_amount_decimal);unit<-text(row$event_summary$unit_price_decimal)
        if(nzchar(gross))paste(german(gross),currency)else if(nzchar(unit))paste("Stückpreis",german(unit),currency)else"–"},character(1L)),
      Konto=vapply(rows,function(row)label(catalog$accounts,row$account_ref),character(1L)),
      stringsAsFactors=FALSE,check.names=FALSE)
  },striped=TRUE,spacing="xs",width="100%")
  statement_block_reasons<-shiny::reactiveVal(NULL)
  shiny::observeEvent(input$statement_block_reasons_run,{
    batch<-statement_reward_valuation_batch()
    rows<-if(is.list(batch))Filter(function(row)identical(row$validation_status,"blocked")&&!identical(row$status,"committed"),batch$drafts)else list()
    if(!length(rows)){statement_block_reasons(NULL);return()}
    shown<-utils::head(rows,25L)
    safe(shiny::withProgress(message="Gründe werden gelesen",value=NULL,
      data_activity_draft_block_reasons_v1(activity_draft_center,activity_editor,runtime$context,vapply(shown,`[[`,character(1L),"draft_handle"))),
      function(reasons)statement_block_reasons(list(reasons=reasons,total=length(rows))))
  })
  # Ein anderer Stapel, andere Gruende: Die Anzeige gilt nur fuer den Stand, an dem sie gelesen wurde.
  shiny::observeEvent(statement_reward_valuation_batch(),statement_block_reasons(NULL),ignoreNULL=FALSE,ignoreInit=TRUE)
  output$statement_block_reasons_state<-shiny::renderUI({
    value<-statement_block_reasons();if(is.null(value))return(NULL)
    texts<-vapply(value$reasons,function(reason)paste(reason$title,"–",reason$copy),character(1L))
    groups<-unique(texts)
    shiny::tagList(
      shiny::tags$ul(lapply(groups,function(group)shiny::tags$li(shiny::strong(sprintf("%d × ",sum(texts==group))),group))),
      if(value$total>length(value$reasons))shiny::p(class="pl-field-hint",sprintf("Gezeigt sind die ersten %d von %d blockierten Rewards.",length(value$reasons),value$total))else NULL)
  })
  output$statement_reward_collision_guided<-shiny::renderUI({
    preview<-statement_reward_collision_preview();if(is.null(preview))return(NULL)
    shiny::div(class="pl-editor-actions",shiny::p(sprintf("%d verschieden · %d wahrscheinlich doppelt · %d ungeklärt",as.integer(preview$distinct_same_time_count),as.integer(preview$probable_duplicate_count),as.integer(preview$unresolved_count))),
      if(identical(preview$status,"confirmation_required"))shiny::tags$button(type="button",class="btn btn-primary action-button",onclick="var c=document.getElementById('statement_reward_collision_confirm');if(c){c.checked=true;Shiny.setInputValue('statement_reward_collision_confirm',true,{priority:'event'});}setTimeout(function(){var b=document.getElementById('statement_reward_collision_apply');if(b){b.click();}},120);return false;","Reihenfolge bestätigen")else NULL)
  })
  output$statement_exchange_status<-shiny::renderUI({statement_status_panel(statement_exchange_state())})
  output$statement_exchange_tuples<-shiny::renderTable({value<-statement_exchange_preview();if(is.null(value))return(NULL);data_statement_exchange_preview_tuples_v1(value,"EUR")},bordered=TRUE,striped=TRUE,spacing="s")
  output$statement_exchange_mapping_controls<-shiny::renderUI({
    value<-statement_exchange_preview();catalog<-activity_catalog();if(is.null(value)||is.null(catalog))return(NULL)
    # After preparing, the mapping is fixed; it stays readable under "Zeilen im Detail".
    if(!is.null(statement_exchange_handoff()))return(NULL)
    tuples<-data_statement_exchange_preview_tuples_v1(value);if(!nrow(tuples))return(shiny::p("Keine Reward-Zuordnung erforderlich."))
    assets<-c("Noch nicht zuordnen"="",choice_vector(catalog$assets));accounts<-c("Noch nicht zuordnen"="",choice_vector(catalog$accounts));profile<-statement_exchange_profile()
    defaults<-if(is.null(profile))list(asset_refs=rep("",nrow(tuples)),account_refs=rep("",nrow(tuples)),stale_target_count=0L)else data_statement_import_mapping_profile_defaults_v1(tuples,profile,function(id)data_asset_activity_editor_ref_for_internal_v1(activity_editor,runtime$context,"asset",id),function(id)data_asset_activity_editor_ref_for_internal_v1(activity_editor,runtime$context,"account",id))
    defaults$asset_refs<-data_statement_import_mapping_suggest_assets_v1(tuples,defaults$asset_refs,catalog$assets)
    # Konto vorbelegt (rc.343), in dieser Reihenfolge: die gespeicherte Wahl je Coin; die Spur des Coins (juengster Reward, sonst
    # juengste Umbuchung auf ein Wallet der Boerse; Kaeufe zaehlen nicht); das einzige Wallet der Boerse; zuletzt das Konto anderer
    # Coins desselben Unterkontos - nur wo der Export eines nennt (Kraken). Sonst bleibt das Feld leer.
    selection<-tryCatch(.data_asset_activity_selection(activity_editor,runtime$context),error=function(error)NULL)
    # Ruhende Konten (#529 Punkt 1) bietet der Reward-Import nicht an.
    resting<-data_resting_account_ids_v1(statement_archive_service)
    if(length(resting)&&!is.null(selection))accounts<-c("Noch nicht zuordnen"="",choice_vector(Filter(function(row){
      account<-tryCatch(.data_asset_activity_resolve(selection,"accounts",row$ref),error=function(error)NULL);is.null(account)||!account$account_id%in%resting},catalog$accounts)))
    defaults$account_refs<-data_statement_import_mapping_suggest_accounts_v1(defaults$asset_refs,defaults$account_refs,
      function(asset_ids)securities_statement_service$reward_accounts(shiny::isolate(input$statement_exchange_adapter),asset_ids),
      function(ref)if(is.null(selection))NULL else .data_asset_activity_resolve(selection,"assets",ref)$asset_id,
      function(id)data_asset_activity_editor_ref_for_internal_v1(activity_editor,runtime$context,"account",id))
    adapter_now<-shiny::isolate(input$statement_exchange_adapter)
    named<-data_statement_named_subaccounts_v1(shiny::isolate(import_offered()))
    if(is.character(adapter_now)&&length(adapter_now)==1L&&adapter_now%in%names(named))
      defaults$account_refs<-data_statement_import_mapping_propagate_accounts_v1(tuples,defaults$account_refs,skip=named[[adapter_now]])
    warning<-if(defaults$stale_target_count>0L)shiny::p(class="pl-section-copy",sprintf("%d gespeicherte Auswahl ist nicht mehr vorhanden und bleibt deshalb offen.",defaults$stale_target_count))else NULL
    shiny::tagList(warning,lapply(seq_len(nrow(tuples)),function(index)shiny::div(class="pl-form-grid",
      shiny::tags$p(shiny::strong(tuples$`Quell-Asset`[[index]])," · ",tuples$`Quellkonto`[[index]]," · ",tuples$Zeilen[[index]]," Zeilen"),
      shiny::selectInput(paste0("statement_exchange_asset_",index),"Vorhandenes Asset",choices=assets,selected=defaults$asset_refs[[index]]),
      shiny::selectInput(paste0("statement_exchange_account_",index),"Vorhandenes Konto",choices=accounts,selected=defaults$account_refs[[index]])
    )))
  })
  output$statement_exchange_mapping_rows<-shiny::renderTable({value<-statement_exchange_mapping();if(is.null(value))return(NULL);data_statement_import_mapping_rows_v1(value,statement_exchange_booked())},bordered=TRUE,striped=TRUE,spacing="s")
  output$statement_exchange_handoff_summary<-shiny::renderUI({
    value<-statement_exchange_mapping();if(is.null(value))return(NULL);counts<-value$disposition_counts
    booked<-length(statement_exchange_booked());ready<-as.integer(counts$draft_ready)+as.integer(counts$draft_needs_valuation)-booked
    portelyra_status_panel("Letzter Schritt bleibt bearbeitbar",sprintf("%d Rewards können als Entwürfe übernommen werden; davon benötigen %d später eine Bewertung. %d sind bereits gebucht und werden übersprungen. Noch keine Buchung.",ready,as.integer(counts$draft_needs_valuation),booked),tone="warning")
  })
  output$statement_reward_valuation_state<-shiny::renderUI({
    batch<-statement_reward_valuation_batch()
    if(is.null(batch))return(portelyra_status_panel("Noch kein Bewertungsstapel des Auszugs geladen","Nach der Reward-Vorschau können genau die zugehörigen Entwürfe geladen werden. Andere Entwürfe bleiben ausgeblendet."))
    if(identical(batch$status,"error"))return(portelyra_status_panel("Reward-Bewertung blockiert",pl_error_text_v1(batch$error_code),tone="error"))
    portelyra_status_panel("Bewertungen des Auszugs geladen",sprintf("%d Rewards · %d offen · %d mit Marktnachweis · %d manuell vollständig · %d aus CSV belegt",batch$draft_count,batch$valuation_pending_count,batch$market_evidence_count,batch$owner_manual_count,batch$source_provided_count),tone=if(batch$valuation_pending_count>0L)"warning"else"positive")
  })
  output$statement_reward_market_batch_state<-shiny::renderUI({
    preview<-statement_reward_market_batch_preview();result<-statement_reward_market_batch_result()
    if(!is.null(result)){if(identical(result$status,"error"))return(portelyra_status_panel("Bewertungsstapel blockiert",pl_error_text_v1(result$error_code),tone="error"));return(portelyra_status_panel(if(identical(result$status,"complete"))"Bewertungsstapel vollständig übernommen"else"Bewertungsstapel teilweise übernommen",paste(result$valuation_applied_count,"Bewertungen gespeichert ·",result$blocked_count,"blockiert · 0 still verworfen · kein Schreiben in die Stammdaten"),tone=if(identical(result$status,"complete"))"positive"else"warning"))}
    if(is.null(preview))return(NULL)
    portelyra_status_panel(if(identical(preview$status,"confirmation_required"))"Persistierte Bewertungsstapel-Vorschau bereit"else"Keine vollständige persistierte Bewertung verfügbar",paste(preview$ready_count,"bereit ·",preview$blocked_count,"blockiert · 0 still verworfen · kein Kursabruf · noch kein Schreiben eines Entwurfs"),tone=if(preview$blocked_count>0L)"warning"else"positive")
  })
  output$statement_reward_valuation_editor<-shiny::renderUI({
    model<-statement_reward_valuation_open();catalog<-activity_catalog();if(is.null(model)||is.null(catalog))return(NULL)
    label_for<-function(rows,ref){matches<-Filter(function(row)identical(row$ref,ref),rows);if(length(matches)==1L)matches[[1L]]$label else "Unbekannt"}
    # Auswahl des Rewards (#520): stand bis rc.343 bei den Einzelschritten, sodass in der geführten Karte nur der erste Reward ohne
    # Wert bearbeitbar war. Angeboten werden die offenen Rewards ohne Wert.
    batch<-statement_reward_valuation_batch()
    offen<-if(is.list(batch))Filter(function(row)identical(row$valuation_summary$lifecycle,"valuation_pending")&&!identical(row$status,"committed"),batch$drafts)else list()
    auswahl<-if(length(offen)>1L){
      handles<-vapply(offen,`[[`,character(1L),"draft_handle")
      labels<-vapply(offen,function(row)paste(row$event_summary$local_date,row$event_summary$local_time,"·",label_for(catalog$assets,row$asset_ref),"· Menge",row$event_summary$quantity_decimal),character(1L))
      shiny::selectInput("statement_reward_valuation_select",sprintf("Reward (%d ohne Wert)",length(offen)),choices=stats::setNames(handles,labels),
        selected=if(isTRUE(model$draft_handle%in%handles))model$draft_handle else handles[[1L]])
    }else NULL
    summary<-shiny::tagList(auswahl,shiny::p(class="pl-section-copy",paste(model$event_summary$local_date,"·",label_for(catalog$assets,model$asset_ref),"·",label_for(catalog$accounts,model$account_ref),"· Menge",model$event_summary$quantity_decimal)))
    if(identical(model$valuation_summary$lifecycle,"source_provided"))return(shiny::tagList(summary,portelyra_status_panel("Bewertung aus CSV geschützt","Dieser Quellwert hat höchste Priorität und kann hier nicht überschrieben werden.",tone="positive")))
    if(!isTRUE(model$can_edit))return(shiny::tagList(summary,portelyra_status_panel("Reward-Entwurf ist nicht mehr bearbeitbar","Die Bewertung wird nur angezeigt; eine Änderung benötigt einen separaten Korrekturworkflow.",tone="warning")))
    currency<-model$valuation_summary$price_currency;if(is.null(currency)||!nzchar(currency))currency<-"EUR"
    market_controls<-shiny::div(class="pl-write-boundary",
      shiny::actionButton("statement_reward_market_prepare","Persistierte Bewertung prüfen",class="btn-default"),
      shiny::checkboxInput("statement_reward_market_confirm","Persistierten Markt- beziehungsweise FX-Beleg ausdrücklich als Bewertung bestätigen",FALSE),
      shiny::actionButton("statement_reward_market_apply","Bestätigte Marktbewertung als neue Fassung des Entwurfs speichern",class="btn-primary"),
      shiny::uiOutput("statement_reward_market_preview")
    )
    if(identical(model$valuation_summary$origin,"source_provided"))return(shiny::tagList(summary,portelyra_status_panel("CSV-Wert benötigt Währungsumrechnung","Der vorrangige Quellwert bleibt unverändert; ergänzt wird ausschließlich ein bestätigter, gespeicherter FX-Beleg.",tone="warning"),market_controls))
    shiny::tagList(summary,shiny::div(class="pl-write-boundary",
      shiny::div(class="pl-form-grid",
        shiny::selectInput("statement_reward_valuation_mode","Bewertungsmethode",c("Fiat-Gesamtwert nach Asset-Gebühr"="manual_fiat_total","Exakter Fiat-Stückpreis"="manual_unit_price")),
        shiny::textInput("statement_reward_valuation_value","Exakter Wert",""),
        shiny::textInput("statement_reward_valuation_currency","Währung",currency)
      ),
      shiny::actionButton("statement_reward_valuation_apply","Bewertung speichern und Entwurf validieren",class="btn-primary")
    ),market_controls)
  })
  output$statement_reward_validation_state<-shiny::renderUI({p<-statement_reward_validation_preview();r<-statement_reward_validation_result();if(!is.null(r)){if(identical(r$status,"error"))return(portelyra_status_panel("Validierung des Auszugs blockiert",pl_error_text_v1(r$error_code),tone="error"));return(portelyra_status_panel(if(identical(r$status,"complete"))"Validierung des Auszugs vollständig"else"Validierung des Auszugs teilweise",paste0(paste(r$validated_ready_count,"bereit validiert ·",r$blocked_count,"blockiert · 0 still verworfen · kein Schreiben in die Stammdaten"),data_activity_draft_shift_note_v1(r$shifted_count)),tone=if(identical(r$status,"complete"))"positive"else"warning"))};if(is.null(p))return(NULL);portelyra_status_panel(if(identical(p$status,"nothing_to_validate"))"Keine erneute Validierung erforderlich"else"Validierung des Auszugs vorbereitet",paste(p$candidate_count,"vollständig bewertete Rewards · 0 still verworfen · noch kein Schreiben · kein Schreiben in die Stammdaten"),tone=if(identical(p$status,"nothing_to_validate"))"positive"else"warning")})
  output$statement_reward_collision_state<-shiny::renderUI({p<-statement_reward_collision_preview();r<-statement_reward_collision_result();if(!is.null(r)){if(identical(r$status,"error"))return(portelyra_status_panel("Zeitkollisionsprüfung blockiert",pl_error_text_v1(r$error_code),tone="error"));return(portelyra_status_panel(if(identical(r$status,"complete"))"Gemeinsamer FIFO-Nachweis vollständig vorbereitet"else"FIFO-Nachweis teilweise vorbereitet",paste(r$source_order_group_ready_count,"erneut validierungsbereit ·",r$blocked_count,"weiter blockiert · 0 still verworfen · noch kein Schreiben in die Stammdaten"),tone=if(identical(r$status,"complete"))"positive"else"warning"))};if(is.null(p))return(NULL);portelyra_status_panel("Zeitgleiche Rewards klassifiziert",paste(p$exact_replay_count,"bereits committed ·",p$distinct_same_time_count,"fachlich verschieden ·",p$probable_duplicate_count,"wahrscheinliche Duplikate ·",p$unresolved_count,"ungeklärt · 0 still verworfen"),tone=if(p$probable_duplicate_count>0L||p$unresolved_count>0L)"warning"else"positive")})
  output$statement_reward_canonical_state<-shiny::renderUI({p<-statement_reward_canonical_preview();r<-statement_reward_canonical_result();if(!is.null(r)){if(identical(r$status,"error"))return(portelyra_status_panel("Kanonische Reward-Übernahme blockiert",pl_error_text_v1(r$error_code),tone="error"));return(portelyra_status_panel(if(identical(r$status,"complete"))"Kanonische Reward-Übernahme vollständig"else"Kanonische Reward-Übernahme teilweise",paste(r$canonical_committed_count,"kanonisch gebucht ·",r$blocked_count,"blockiert ·",r$activity_generation_updated_count,"Generationen aktualisiert · 0 still verworfen"),tone=if(identical(r$status,"complete"))"positive"else"warning"))};if(is.null(p))return(NULL);portelyra_status_panel(if(identical(p$status,"nothing_to_commit"))"Keine validierten Rewards zu buchen"else"Kanonische Reward-Übernahme vorbereitet",paste(p$candidate_count,"validierte Rewards · jeder Schreibvorgang wird frisch gegen FIFO geprüft · 0 still verworfen · noch kein Schreiben"),tone=if(identical(p$status,"nothing_to_commit"))"positive"else"warning")})
  output$statement_reward_canonical_rows<-shiny::renderTable({r<-statement_reward_canonical_result();if(is.null(r)||is.null(r$dispositions))return(data.frame());do.call(rbind,lapply(r$dispositions,function(row)data.frame(Zeile=row$source_row_ordinal,Disposition=row$disposition,`Buchungsbestand aktualisiert`=isTRUE(row$activity_generation_updated),Fehler=if(is.null(row$error_code))""else row$error_code,check.names=FALSE)))})
  output$statement_reward_market_preview<-shiny::renderUI({p<-statement_reward_market_preview();if(is.null(p))return(NULL);if(!is.null(p$error_code))return(portelyra_status_panel("Kein gespeicherter Kurs für diesen Reward",data_statement_reward_valuation_message_v1(p$error_code),tone="warning"));shiny::tagList(portelyra_status_panel("Gespeicherte Bewertung zum Tagesschlusskurs bereit",paste(p$local_date,"·",p$fx_route,"· FX-Quelldatum",if(is.null(p$fx_observation_date))"identisch"else p$fx_observation_date,"· Alter",if(is.null(p$fx_rate_age_days))0L else p$fx_rate_age_days,"Tag(e) · kein Kursabruf · noch kein Schreiben eines Entwurfs"),tone="warning"),shiny::tableOutput("statement_reward_market_preview_table"))})
  output$statement_reward_market_preview_table<-shiny::renderTable({p<-statement_reward_market_preview();if(is.null(p)||!is.null(p$error_code))return(data.frame());data.frame(Methode=p$mode,Datum=p$local_date,`Menge netto`=p$eligible_quantity_decimal,Einheitswert=if(is.null(p$unit_price_decimal))"nicht erforderlich"else p$unit_price_decimal,`Wert gesamt`=p$fiat_total_decimal,Währung=p$valuation_currency,`Umrechnung`=p$fx_route,`Wechselkurs vom`=if(is.null(p$fx_observation_date))"identisch"else p$fx_observation_date,`Alter des Wechselkurses (Tage)`=if(is.null(p$fx_rate_age_days))0L else p$fx_rate_age_days,`Wechselkurs-Auswahl`=if(is.null(p$fx_selection_basis))"identity"else p$fx_selection_basis,Providerzugriff="nein",`Entwurf wird geschrieben`="erst nach Bestätigung",check.names=FALSE)})
  output$statement_reward_valuation_rows<-shiny::renderTable({
    batch<-statement_reward_valuation_batch();catalog<-activity_catalog();if(is.null(batch)||!identical(batch$status,"reward_valuation_batch_ready")||!length(batch$drafts)||is.null(catalog))return(NULL)
    label_for<-function(rows,ref){matches<-Filter(function(row)identical(row$ref,ref),rows);if(length(matches)==1L)matches[[1L]]$label else "Unbekannt"}
    data.frame(Zeile=vapply(batch$drafts,`[[`,integer(1L),"source_row_ordinal"),Datum=vapply(batch$drafts,function(row)row$event_summary$local_date,character(1L)),Asset=vapply(batch$drafts,function(row)label_for(catalog$assets,row$asset_ref),character(1L)),Konto=vapply(batch$drafts,function(row)label_for(catalog$accounts,row$account_ref),character(1L)),Menge=vapply(batch$drafts,function(row)row$event_summary$quantity_decimal,character(1L)),Bewertung=vapply(batch$drafts,function(row)row$valuation_summary$lifecycle,character(1L)),Revision=vapply(batch$drafts,function(row)as.integer(row$revision),integer(1L)),check.names=FALSE,stringsAsFactors=FALSE)
  },bordered=TRUE,striped=TRUE,spacing="s")
  output$statement_mapping_status<-shiny::renderUI({statement_status_panel(statement_mapping_state())})
  output$statement_mapping_tuples<-shiny::renderTable({value<-statement_mapping_result();if(is.null(value))return(NULL);data_statement_import_mapping_tuples_v1(value)},bordered=TRUE,striped=TRUE,spacing="s")
  output$statement_mapping_rows<-shiny::renderTable({value<-statement_mapping_result();if(is.null(value))return(NULL);data_statement_import_mapping_rows_v1(value)},bordered=TRUE,striped=TRUE,spacing="s")
  output$statement_workspace_status<-shiny::renderUI({statement_status_panel(statement_workspace_state())})
  output$statement_workspace_profile<-shiny::renderUI({
    review<-statement_workspace_result();if(is.null(review))return(NULL);profile<-review$source_profile
    shiny::tags$div(
      class="portelyra-note",
      sprintf(
        "%s:%s · %s/%s/%s · Header %s (%d Spalten) · Abnahme %s",
        profile$source_profile_id,profile$source_profile_revision,profile$institution,profile$medium,profile$locale,
        profile$header_status,profile$column_count,profile$private_owner_uat_status
      )
    )
  })
  output$statement_workspace_columns<-shiny::renderTable({review<-statement_workspace_result();if(is.null(review))return(NULL);data_statement_import_workspace_column_table_v1(review)},bordered=TRUE,striped=TRUE,spacing="s")
  output$statement_workspace_routes<-shiny::renderTable({review<-statement_workspace_result();if(is.null(review))return(NULL);data_statement_import_workspace_route_table_v1(review)},bordered=TRUE,striped=TRUE,spacing="s")
  output$statement_workspace_catalog<-shiny::renderTable({review<-statement_workspace_result();if(is.null(review))return(NULL);data_statement_import_workspace_catalog_table_v1(review)},bordered=TRUE,striped=TRUE,spacing="s")
  output$statement_workspace_valuation<-shiny::renderUI({
    review<-statement_workspace_result();if(is.null(review))return(NULL);valuation<-review$valuation_review
    copy<-if(is.null(valuation$manual_input)) {
      "Reward-Basis fehlt sichtbar; kein Candidate ist dadurch automatisch bewertet."
    } else {
      paste(
        valuation$manual_input$amount_input_mode,"·",valuation$manual_input$price_currency,
        "· exakte lokale Zone",valuation$manual_input$exact_local_zone,
        "· Bruttowert",valuation$manual_input$gross_income_decimal,
        "· kein Runden"
      )
    }
    portelyra_status_panel("Manuelle Reward-Bewertung · synthetisch",paste(copy,"· Übergabe an den Kursanbieter deaktiviert."),tone=if(is.null(valuation$manual_input))"warning"else"neutral")
  })
  output$statement_workspace_counts<-shiny::renderTable({review<-statement_workspace_result();if(is.null(review))return(NULL);data_statement_import_workspace_count_table_v1(review)},bordered=TRUE,striped=TRUE,spacing="s")
  output$statement_workspace_rows<-shiny::renderTable({review<-statement_workspace_result();if(is.null(review))return(NULL);data_statement_import_workspace_row_table_v1(review)},bordered=TRUE,striped=TRUE,spacing="xs")

  output$portfolio_exchange_path_view <- shiny::renderUI({
    model<-portfolio_exchange_paths_model();if(is.null(model))return(portelyra_status_panel("Ordner noch nicht angezeigt","Ordner anzeigen liest nur den vertrauenswürdigen Runtime-Kontext."))
    shiny::div(
      portelyra_status_panel(if(isTRUE(model$initialized))"Austauschordner bereit"else"Austauschordner noch nicht angelegt",if(isTRUE(model$initialized))"Diese Pfade sind vollständig lokal und nur für den Eigentümer zugänglich."else"Mit separater Bestätigung anlegen.",tone=if(isTRUE(model$initialized))"neutral"else"warning"),
      shiny::tags$p(shiny::tags$strong("Lokaler Datenordner für Transaktionen und Aktivitäten: "),shiny::tags$code(model$product_data_path)),
      shiny::tags$p(shiny::tags$strong("Eingangsordner für neue Portfolio- und Transaktionspakete: "),shiny::tags$code(model$import_inbox_path)),
      shiny::tags$p(shiny::tags$strong("Exporte: "),shiny::tags$code(model$export_path)),
      shiny::tags$p(shiny::tags$strong("Verlustfrei übernommene Imports: "),shiny::tags$code(model$staged_import_path))
    )
  })
  output$portfolio_exchange_export_state <- shiny::renderUI({
    model<-portfolio_exchange_export_model();if(is.null(model))return(portelyra_status_panel("Noch keine Exportvorschau","Der Export erfolgt ohne externen Datenabruf und liest den aktuellen Bestand nur lesend."))
    portelyra_status_panel(if(identical(model$status,"completed"))"Export abgeschlossen"else"Export wartet auf Bestätigung",paste(model$record_count,"Datensätze ·",model$asset_file_count,"Asset-Dateien ·",model$account_file_count,"Konto-/Wallet-Dateien · Dezimalzeichen ,"),tone=if(identical(model$status,"completed"))"neutral"else"warning")
  })
  output$portfolio_exchange_import_state <- shiny::renderUI({
    model<-portfolio_exchange_import_model();if(is.null(model))return(portelyra_status_panel("Noch keine Importvorschau","Paket in den sichtbaren Eingangsordner kopieren und den Eingangsordner lesen."))
    portelyra_status_panel(if(identical(model$status,"staged_lossless_ready_for_domain_handoffs"))"Paket verlustfrei im Eingangsordner"else"Import wartet auf Bestätigung",paste(model$record_count,"Datensätze · Redundanz",model$redundancy_status,"· Schreiben in den Bestand aus"),tone="warning")
  })
  output$portfolio_exchange_handoff_state<-shiny::renderUI({model<-portfolio_exchange_handoff_model();if(is.null(model))return(portelyra_status_panel("Noch keine Vorschau je Bereich","Zuerst ein vorgemerktes Paket und genau einen Bereich auswählen."));portelyra_status_panel(if(model$status%in%c("completed","already_completed","recovered_completed"))"Übergabe je Bereich abgeschlossen"else"Übergabe je Bereich wartet auf Bestätigung",paste(model$domain,"·",model$source_record_count,"Quelldatensätze ·",if(is.null(model$created_count))model$create_count else model$created_count,"Wirkungen"),tone=if(model$status%in%c("completed","already_completed","recovered_completed")&&!isTRUE(model$candidate_only))"neutral"else"warning")})
  output$portfolio_exchange_recovery_state<-shiny::renderUI({model<-portfolio_exchange_recovery_model();if(is.null(model))return(portelyra_status_panel("Keine Wiederaufnahme ausgewählt","Die Wiederaufnahme gleicht einen verbrauchten Versuch vor jeder Fortsetzung ab."));portelyra_status_panel(if(model$status%in%c("recovered_completed","already_completed"))"Wiederaufnahme abgeschlossen"else"Wiederaufnahme wartet auf eigene Bestätigung",paste("Bereich",model$domain,"·",if(is.null(model$effect_state))model$status else model$effect_state),tone=if(model$status%in%c("recovered_completed","already_completed"))"neutral"else"warning")})
  output$portfolio_exchange_cash_state<-shiny::renderUI({model<-portfolio_exchange_cash_list();selected<-portfolio_exchange_cash_model();if(!is.null(selected))return(portelyra_status_panel("Cash-Candidate an gemeinsame Vorschau übergeben",paste(selected$action_type,"· separate Cash-One-Use-Bestätigung erforderlich"),tone="warning"));if(is.null(model))return(portelyra_status_panel("Cash-Vorschläge noch nicht gelesen","Erst nach abgeschlossener Übergabe an den Bereich Cash verfügbar."));ready<-sum(vapply(model$candidates,function(item)identical(item$status,"ready_for_cash_review"),logical(1L)));blocked<-sum(vapply(model$candidates,function(item)identical(item$status,"blocked_dependency"),logical(1L)));portelyra_status_panel("Übergabe geprüfter Cash-Vorschläge",paste(ready,"bereit ·",blocked,"durch abhängige Ereignisse blockiert · kein Schreiben von Cash-Fakten"),tone=if(ready)"warning"else"neutral")})

  output$asset_center_search_state <- shiny::renderUI({
    current <- action_feedback$read('search')
    if(!is.null(current))return(data_action_feedback_panel_v1(current))
    result <- asset_center_provider_search_result(); preview <- asset_center_provider_search_preview()
    if(!is.null(result))return(portelyra_status_panel(paste(length(result$candidates),'Suchvorschläge verfügbar'), 'Auswahl prüfen und bei Bedarf nur ins Formular übernehmen. Noch keine Zuordnung gespeichert.'))
    if(!is.null(preview))return(portelyra_status_panel('Suchvorschau bereit','Genau diesen Suchabruf separat bestätigen. Noch kein Abruf.',tone='warning'))
    shiny::p('Noch keine aktuelle Suche. Bei Bedarf Suchvorschau erstellen; Tippen allein startet keinen Abruf.')
  })
  output$runtime_status <- shiny::renderUI({
    current <- state()
    portelyra_status_panel(current$title, current$copy, tone = current$tone)
  })
  output$workspace_status <- shiny::renderUI({
    model <- workspace()
    if (is.null(model)) return(portelyra_status_panel("Wird gelesen", "Die Übersicht liest die Stammdaten, sobald sie aufgeklappt ist."))
    portelyra_status_panel(
      if (model$status == "ready") "Daten bereit" else if (model$status == "empty") "Noch keine Daten erfasst" else "Noch nicht eingerichtet",
      "Stand der lokal gespeicherten Stammdaten."
    )
  })
  output$workspace_counts <- shiny::renderUI({
    model <- workspace(); if (is.null(model)) return(NULL)
    shiny::div(class = "pl-kpi-grid", lapply(names(model$counts), function(name) {
      labels <- c(portfolio_count = "Portfolios", account_count = "Konten", asset_count = "Assets", transaction_count = "Buchungen",
                  current_transaction_count = "gültige Buchungen")
      portelyra_kpi_item(if (name %in% names(labels)) unname(labels[[name]]) else gsub("_count$", "", name), as.character(model$counts[[name]]))
    }))
  })
  rows <- function(name, archived = FALSE) {
    model <- workspace(); if (is.null(model) || !length(model[[name]])) return(NULL)
    picked <- Filter(function(row) identical(row$status, "archived") == archived, model[[name]]); if (!length(picked)) return(NULL)
    as.data.frame(do.call(rbind, lapply(picked, function(row) unlist(row, use.names = TRUE))), stringsAsFactors = FALSE)
  }
  output$workspace_archive <- shiny::renderTable({
    parts <- Filter(Negate(is.null), lapply(c(Portfolio = "portfolios", Konto = "accounts", Asset = "assets"), function(name) {
      frame <- rows(name, archived = TRUE); if (is.null(frame)) NULL else data.frame(Bereich = name, Name = frame$name, stringsAsFactors = FALSE)
    }))
    if (!length(parts)) return(data.frame(Hinweis = "Nichts archiviert."))
    frame <- do.call(rbind, parts); frame$Bereich <- c(portfolios = "Portfolio", accounts = "Konto", assets = "Asset")[frame$Bereich]; frame
  }, striped = TRUE, bordered = FALSE)
  # Deutsche Spalten und Werte statt der Felder des Kerns (#490).
  workspace_frame <- function(name) {
    frame <- rows(name); if (is.null(frame)) return(NULL)
    types <- switch(name, accounts = PL_ACCOUNT_TYPE_LABELS_V1, assets = PL_ASSET_TYPE_LABELS_V1, transactions = PL_EVENT_TYPE_LABELS_V1, NULL)
    if ("type" %in% names(frame) && !is.null(types)) frame$type <- pl_label_v1(types, frame$type)
    if ("status" %in% names(frame)) frame$status <- pl_label_v1(PL_RECORD_STATUS_LABELS_V1, frame$status)
    if ("state" %in% names(frame)) frame$state <- pl_label_v1(c(current = "gültig", void = "storniert"), frame$state)
    if ("date" %in% names(frame)) frame$date <- pl_day_v1(frame$date)
    labels <- c(name = "Name", currency = if (identical(name, "assets")) "Kurswährung" else "Währung", status = "Stand",
                type = if (identical(name, "assets")) "Klasse" else "Art", date = "Datum", state = "Stand")
    known <- names(frame) %in% names(labels)
    names(frame)[known] <- unname(labels[names(frame)[known]])
    frame
  }
  output$workspace_portfolios <- shiny::renderTable(workspace_frame("portfolios"), striped = TRUE, bordered = FALSE)
  output$workspace_accounts <- shiny::renderTable(workspace_frame("accounts"), striped = TRUE, bordered = FALSE)
  output$workspace_assets <- shiny::renderTable(workspace_frame("assets"), striped = TRUE, bordered = FALSE)
  output$workspace_transactions <- shiny::renderTable(workspace_frame("transactions"), striped = TRUE, bordered = FALSE)
  output$activity_workflow_action <- shiny::renderText({
    view <- activity_workflow_view()
    if (isTRUE(activity_workflow_completed())) 'completed' else if (length(view$selected_refs)>1L) 'void' else if (identical(view$action,'correct') && !isTRUE(view$form_loaded)) 'loading' else view$action
  })
  shiny::outputOptions(output,'activity_workflow_action',suspendWhenHidden=FALSE)
  # Die Adresse der Gegenseite gibt es nur bei Krypto; die Maske zeigt das Feld nur dort (#439).
  activity_asset_is_crypto <- shiny::reactive({
    model <- activity_catalog(); if (is.null(model)) return(FALSE)
    hit <- Filter(function(value) identical(value$ref, input$activity_asset), model$assets)
    length(hit) == 1L && identical(hit[[1L]]$asset_type, "crypto")
  })
  output$activity_asset_is_crypto <- shiny::renderText(if (isTRUE(activity_asset_is_crypto())) "yes" else "no")
  shiny::outputOptions(output, "activity_asset_is_crypto", suspendWhenHidden = FALSE)
  output$activity_workflow_state <- shiny::renderUI({
    view <- activity_workflow_view()
    pending <- !identical(view$selected_refs,workflow_refs())
    title <- if (pending) 'Auswahl noch nicht übernommen' else if (isTRUE(activity_workflow_completed())) 'Korrektur/Storno abgeschlossen' else if (length(view$selected_refs)>1L) paste(length(view$selected_refs),'Buchungen gemeinsam stornieren') else
      if (identical(view$action,'create')) 'Neuanlage · keine Buchung ausgewählt' else if (identical(view$action,'void')) 'Storno · genau eine Buchung' else 'Bearbeitung · genau eine Buchung'
    copy <- if (pending) 'Auswahl übernehmen. Nicht gespeicherte Eingaben bleiben bis zur ausdrücklichen Verwerfentscheidung erhalten.' else
      if (isTRUE(activity_workflow_completed())) 'Keine weitere Speicherung nötig. Für eine neue Transaktion die Buchungsauswahl leeren und übernehmen; zum Bearbeiten die jetzt aktive Buchung auswählen.' else
      if (length(view$selected_refs)>1L) 'Keine Sammelbearbeitung. Alle ausgewählten Buchungen werden nach gemeinsamer Vorschau und Bestätigung atomar storniert. Historische Generationen bleiben erhalten; Cash bleibt unverändert.' else
      if (identical(view$action,'create')) 'Neue Transaktion · genau ein Non-Cash-Asset. Vorhandene Buchungen werden nicht verändert.' else
      if (identical(view$action,'void')) 'Nur die ausgewählte Buchung stornieren. Ersatzfelder sind nicht erforderlich; FIFO-Folgewirkungen zuerst prüfen.' else
      if (!isTRUE(view$form_loaded)) 'Die ausgewählte Buchung wird in die gemeinsame Maske geladen. Erst nach vollständiger Übernahme prüfen.' else
      'Geladene Buchung in der gemeinsamen Maske bearbeiten und Korrektur prüfen. Keine Neuanlage.'
    portelyra_status_panel(title,copy,tone=if(pending || length(view$selected_refs)>1L)'warning'else'neutral')
  })
  output$activity_asset_fee_notice <- shiny::renderText({
    fee <- input$activity_asset_fee
    if (is.null(fee) || !nzchar(trimws(fee)) || !activity_takes()("asset_fee")) return("")
    paste("Zusatzangabe: Gebühr in Asset-Einheiten =", trimws(fee),
          "· bleibt auch bei geschlossenem Bereich erhalten. Unter Weitere Angaben prüfen.")
  })
  output$activity_guided_hint<-shiny::renderUI({
    takes<-activity_takes()
    present<-function(value)is.character(value)&&length(value)==1L&&!is.na(value)&&nzchar(value)
    decimal_valid<-function(value){normalized<-desktop_product_manual_decimal_v1(value);present(normalized)&&!identical(normalized,"0")&&grepl("^(0|[1-9][0-9]*)(\\.[0-9]*[1-9])?$",normalized)}
    date_valid<-inherits(input$activity_date,"Date")&&length(input$activity_date)==1L&&!is.na(input$activity_date)
    completed <- activity_completed()
    if(!is.null(completed)) return(portelyra_status_panel(
      if(isTRUE(completed$fresh)) 'Transaktion abgeschlossen' else 'Buchung gespeichert · Berechnungsstand prüfen',
      if(!isTRUE(completed$fresh)) 'Nicht erneut buchen. Der gespeicherte FIFO-Berechnungsstand muss separat geprüft werden.'
      else if(is.character(completed$position) && length(completed$position)==1L) paste0(completed$position, '. Keine weitere Speicherung nötig. Für eine neue Transaktion die Eingaben ändern.')
      else 'Keine weitere Speicherung nötig. Prüfe bei Bedarf die Asset-Historie. Für eine neue Transaktion die Eingaben ändern.',
      tone=if(isTRUE(completed$fresh))'positive'else'warning'))
    next_step<-"Transaktionsdaten prüfen";copy<-"Prüfe zuerst die Vorschau. Das speichert noch keine Buchung.";tone<-"neutral"
    if(is.null(activity_catalog())){next_step<-"Auswahl laden";copy<-"Zuerst Auswahl aktualisieren. Dabei wird nichts geschrieben."}
    else if(!present(input$activity_portfolio)||!present(input$activity_account)||!present(input$activity_asset)){next_step<-"Ziel vollständig auswählen";copy<-"Portfolio, Konto / Wallet und genau ein Asset wählen."}
    else if(identical(input$activity_type,"transfer")&&!present(input$activity_related_account)){next_step<-"Zielkonto auswählen";copy<-"Für einen internen Transfer ist ein anderes Zielkonto erforderlich."}
    else if(!date_valid){next_step<-"Transaktionsdatum ergänzen";copy<-"Das Datum wird niemals automatisch als aktueller Tag eingesetzt."}
    else if(identical(input$activity_time_evidence,"exact")&&!present(input$activity_time)){next_step<-"Lokale Uhrzeit ergänzen";copy<-"HH:MM oder HH:MM:SS eingeben; UTC wird aus Datum, Uhrzeit und Zeitzone bestimmt."}
    else if(takes("quantity")&&!decimal_valid(input$activity_quantity)){next_step<-"Menge ergänzen";copy<-"Eine positive exakte Dezimalmenge eingeben. Dezimalkomma und Dezimalpunkt sind zulässig; Tausendertrennzeichen nicht."}
    else if(takes("eligible_quantity")&&isTRUE(input$activity_amount_mode%in%c("quantity_unit_price","net_quantity_unit_price"))&&!decimal_valid(input$activity_eligible_quantity)){next_step<-"Dividendenberechtigte Menge ergänzen";copy<-"Die Stückzahl, auf die die Dividende gezahlt wurde; mit dem Stückpreis ergibt sie den Betrag."}
    else if(takes("movement_context")&&isTRUE(input$activity_movement_context%in%c("","not_applicable"))){next_step<-"Anlass wählen";copy<-"Bei Ein- und Auslieferung gehört der Anlass dazu, notfalls „Unklassifiziert“."}
    else if(takes("acquisition")&&(identical(input$activity_acquisition_evidence,"not_applicable")||!inherits(input$activity_acquisition_date,"Date")||!length(input$activity_acquisition_date)||is.na(input$activity_acquisition_date))){next_step<-"Ursprüngliche Anschaffungszeit ergänzen";copy<-"Bei einer Einlieferung zählt, wann die Stücke ursprünglich angeschafft wurden: Datum und Zeitzone, bei „Exakt“ auch die Uhrzeit."}
    else if(identical(input$activity_amount_mode,"quantity_unit_price")&&!decimal_valid(input$activity_unit_price)){next_step<-"Stückpreis ergänzen";copy<-"Wert je Einheit exakt eingeben. Abschließende Nullen werden ohne Rundung kanonisch entfernt."}
    else if(!is.null(activity_net_gross())&&!identical(activity_net_gross()$status,"ready")){next_step<-"Nettobetrag und Steuersatz ergänzen";copy<-data_net_amount_gross_hint_v1(activity_net_gross());tone<-"warning"}
    else if(identical(input$activity_amount_mode,"gross_total")&&!decimal_valid(input$activity_gross_total)){next_step<-"Gesamtbetrag ergänzen";copy<-"Den belegten Brutto-Gesamtbetrag eingeben; es wird kein Stückpreis erfunden."}
    else if(!is.null(scale_preview())){next_step<-"Mengenskala ausdrücklich prüfen";copy<-"Die Vorschau benötigt vor der Transaktion eine separate bestätigte Skalenrevision.";tone<-"warning"}
    else if(!is.null(activity_preview())){next_step<-"Vorschau prüfen und speichern";copy<-"Die angezeigte Mengen-/FIFO-Wirkung kontrollieren. Speichern bucht genau diese Vorschau.";tone<-"warning"}
    portelyra_status_panel(paste("Nächster Schritt ·",next_step),copy,tone=tone)
  })
  output$activity_command_feedback <- shiny::renderUI({
    data_action_feedback_panel_v1(action_feedback$read('activity'))
  })
  output$activity_state <- shiny::renderUI({
    catalog <- activity_catalog(); preview <- activity_preview()
    if (is.null(catalog)) return(portelyra_status_panel("Asset-Auswahl nicht geladen", "„Auswahl aktualisieren“ ist nur lesend und startet keinen Rechenlauf."))
    view <- activity_read_view()
    portelyra_status_panel(
      if (is.null(preview)) "Buchungsmaske bereit" else "FIFO-v2-Vorschau wartet auf Einmalbestätigung",
      paste(length(catalog$assets), "Non-Cash-Assets ·", length(catalog$accounts),
            "Verwahrkonten · FIFO", if (is.null(view)) "unavailable" else view$fifo_state,
            "· automatische Cash-Seite aus"),
      tone=if (is.null(preview) && !is.null(view) && identical(view$fifo_state,"fresh")) "neutral" else "warning"
    )
  })
  output$activity_scope_state <- shiny::renderUI({
    projection <- activity_selection_projection()
    if (is.null(projection)) {
      return(portelyra_status_panel(
        "Asset-Ansicht noch nicht geladen",
        "Aktualisieren liest den Katalog und den vorhandenen FIFO- und Buchungsstand ohne Berechnung."
      ))
    }
    if (identical(projection$status, "blocked")) {
      return(portelyra_status_panel(
        "Asset-Ansicht blockiert", pl_error_text_v1(projection$error_code), tone = "error"
      ))
    }
    if (identical(projection$status, "unavailable")) {
      reason <- switch(
        projection$unavailable_reason,
        unsupported_asset_domain = "Cash benötigt einen getrennten kompatiblen Cash-Read-Stand.",
        current_custody_not_fresh = "Aktueller Kontobezug benötigt einen frischen abgeschlossenen Custody-Stand.",
        holding_interval_not_fresh = "Halten im Zeitraum benötigt den bereits abgeschlossenen frischen FIFO-v2-Stand. Der Filter startet keine Berechnung.",
        read_model_absent = "Der abgeschlossene Lesestand für Buchungen und FIFO fehlt.",
        "Der Nachweis für den gewählten Filter ist nicht verfügbar."
      )
      return(portelyra_status_panel("Asset-Filter nicht verfügbar", reason, tone = "warning"))
    }
    empty <- projection$resolved_asset_count == 0L
    mode_label <- switch(
      projection$scope_mode,
      all = "Alle", manual = "Nur manuell", filter = "Nur Filter",
      union = "Manuell ODER Filter", intersection = "Manuell UND Filter"
    )
    title <- if (empty) {
      "Keine Assets erfüllen den expliziten Auswahlkontext"
    } else if (projection$resolved_asset_count == 1L) {
      "1 Asset in den Lesetabellen"
    } else {
      paste(projection$resolved_asset_count, "Assets in den Lesetabellen")
    }
    account_filter_state <- if (identical(projection$account_filter_status, "available")) {
      "Kontofilter verfügbar"
    } else "Kontofilter nicht verfügbar"
    interval_state <- if (!isTRUE(projection$interval_enabled)) {
      "Zeitraumfilter aus"
    } else {
      paste0(
        "Zeitraum ", if (is.null(projection$interval_from)) "offen" else projection$interval_from,
        " bis ", if (is.null(projection$interval_to)) "offen" else projection$interval_to,
        " · ", projection$interval_relation, " / ", projection$holding_mode,
        " · ", projection$interval_filter_status
      )
    }
    copy <- paste(
      "Modus", mode_label, "·", projection$manual_asset_count, "manuell ·",
      projection$filter_asset_count, "per Filter ·", projection$excluded_asset_count, "ausgeschlossen ·",
      projection$selected_account_count, "Konten ·", projection$account_usage, "/", projection$account_match, "·",
      account_filter_state, "·", interval_state, "· Opening-Kontext",
      projection$opening_context_event_count, "Ereignisse ·", projection$visible_position_count, "FIFO-Welten ·",
      projection$visible_custody_position_count, "Verwahrbestände ·",
      projection$visible_event_count, "Buchungen · Ziel-Asset des Schreibformulars getrennt"
    )
    tone <- if (empty || !identical(projection$fifo_state, "fresh") ||
      !identical(projection$account_filter_status, "available") ||
      identical(projection$interval_filter_status, "unavailable")) "warning" else if (
      identical(projection$scope_mode, "all")
    ) "neutral" else "positive"
    portelyra_status_panel(title, copy, tone = tone)
  })
  output$activity_interval_states <- shiny::renderTable({
    projection <- activity_selection_projection()
    if (is.null(projection) || !isTRUE(projection$interval_enabled) ||
        !projection$status %in% c("ready", "empty")) return(data.frame())
    rows <- unlist(lapply(projection$portfolios, function(portfolio) {
      lapply(portfolio$interval_asset_states, function(row) list(
        Portfolio = portfolio$portfolio_label,
        Asset = row$asset_selection_label,
        `Buchungen im Zeitraum` = if (isTRUE(row$activity_in_interval)) "ja" else "nein",
        `Gehalten im Zeitraum` = if (is.null(row$held_in_interval)) "nicht benötigt" else if (isTRUE(row$held_in_interval)) "ja" else "nein",
        `Menge zu Beginn` = pl_quantity_v1(row$opening_quantity_decimal, "—"),
        `Menge am Ende` = pl_quantity_v1(row$closing_quantity_decimal, "—"),
        `Ereignisse vor Beginn` = row$opening_context_event_count
      ))
    }), recursive = FALSE)
    desktop_workflow_rows_frame_v1(rows)
  }, striped = TRUE, bordered = TRUE)
  activity_exact_display <- function(value) data_exact_ratio_presentation_v1(
    value, show_exact=isTRUE(input$activity_show_exact_ratios), decimal_places=8L
  )
  # Betraege mit Einheit, Kurse ohne Nullen am Ende (#529 Punkt 8). Mit „Exakte Brüche anzeigen“ bleibt der Wert, wie der
  # Kern ihn fuehrt; sonst wird ein Bruch auf zwoelf Stellen abgeschnitten und fuer die Anzeige gerundet.
  activity_decimal_text <- function(value) {
    if (is.null(value)) return("")
    text <- as.character(value)
    if (length(text) == 1L && !is.na(text) && grepl("^-?[0-9]+/[1-9][0-9]*$", text)) {
      parts <- strsplit(text, "/", fixed = TRUE)[[1L]]
      text <- sub("\u2026$", "", .data_exact_ratio_truncated_decimal_v1(parts[[1L]], parts[[2L]], 12L))
    }
    text
  }
  activity_utc_text <- function(value) {
    parsed <- suppressWarnings(as.POSIXct(as.character(value), format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
    if (length(parsed) != 1L || is.na(parsed)) as.character(value) else paste(format(parsed, "%d.%m.%Y %H:%M:%S", tz = "UTC"), "UTC")
  }
  activity_money <- function(value, currency) if (isTRUE(input$activity_show_exact_ratios)) activity_exact_display(value)
    else pl_amount_v1(activity_decimal_text(value), currency, 2L, "—")
  activity_price <- function(value, currency) if (isTRUE(input$activity_show_exact_ratios)) activity_exact_display(value)
    else pl_price_v1(activity_decimal_text(value), currency, "—")
  # Fachliche Spaltenbezeichnungen statt interner Feldnamen. Umbenannt wird
  # nach dem Aufbau des Frames, damit data.frame() Leer- und Sonderzeichen in
  # den Bezeichnungen nicht umschreibt.
  activity_german_frame <- function(frame) {
    if (!is.data.frame(frame) || !ncol(frame)) return(frame)
    labels <- c(
      Portfolio = "Portfolio", FIFO_World = "FIFO-Welt", Asset = "Asset", Asset_Type = "Asset-Typ",
      Currency = "Währung", Quantity = "Menge", FIFO_Basis = "Einstandswert", Cost_Average = "Ø Einstandskurs",
      Realized_Proceeds = "Realisierter Erlös", Realized_FIFO_Basis = "Einstandswert verkauft",
      Realized_GuV = "Realisierte GuV", Income = "Ertrag", Fees = "Gebühren", FIFO_Authority = "FIFO-Grundlage",
      Account = "Konto / Wallet", Custody_Dimension = "Verwahrart", Date = "Datum", Time = "Zeitpunkt",
      Event = "Ereignis", Related_Account = "Gegenkonto", Amount = "Betrag",
      FIFO_Basis_Added = "FIFO-Basis zugeführt", FIFO_Basis_Consumed = "FIFO-Basis verbraucht",
      Proceeds = "Erlös", Cash_Delta = "Cash-Wirkung", Semantic_Contract = "Vertrag",
      Calculation_Status = "Berechnungsstatus", Automatic_Cash = "Automatisches Cash"
    )
    known <- names(frame) %in% names(labels)
    names(frame)[known] <- unname(labels[names(frame)[known]])
    frame
  }
  activity_position_frame <- function(projection) {
    if (is.null(projection) || !projection$status %in% c("ready", "empty")) return(data.frame())
    rows <- unlist(lapply(projection$portfolios, function(portfolio) lapply(portfolio$positions, function(row) list(
      Portfolio=portfolio$portfolio_label, Asset=row$asset_selection_label,
      Asset_Type=pl_label_v1(PL_ASSET_TYPE_LABELS_V1, row$asset_type), Quantity=pl_quantity_v1(row$remaining_quantity_decimal, "—"),
      FIFO_Basis=activity_money(row$remaining_fifo_basis, row$currency),
      Cost_Average=if (is.null(row$cost_average)) "—" else activity_price(row$cost_average, row$currency),
      Realized_Proceeds=activity_money(row$realized_gross_proceeds, row$currency),
      Realized_FIFO_Basis=activity_money(row$realized_fifo_basis, row$currency),
      Realized_GuV=activity_money(row$realized_gain_before_tax, row$currency), Income=activity_money(row$gross_income, row$currency),
      Fees=activity_money(row$monetary_fees, row$currency)
    ))), recursive=FALSE)
    activity_german_frame(desktop_workflow_rows_frame_v1(rows))
  }
  output$activity_positions <- shiny::renderTable(activity_position_frame(activity_selection_projection()),striped=TRUE,bordered=TRUE)
  output$activity_context_positions <- shiny::renderTable(activity_position_frame(activity_context_projection()),striped=TRUE,bordered=TRUE)
  # `marked`: das Konto im Formular. Dann je Konto nur Konto, Menge und die Markierung - es geht um ein Asset (rc.335).
  activity_custody_frame <- function(projection, marked = NULL) {
    if (is.null(projection) || !projection$status %in% c("ready", "empty")) return(data.frame())
    rows <- unlist(lapply(projection$portfolios, function(portfolio) lapply(portfolio$custody_positions, function(row)
      if (is.null(marked)) list(
        Portfolio=portfolio$portfolio_label, Account=row$account_selection_label, Asset=row$asset_selection_label,
        Asset_Type=pl_label_v1(PL_ASSET_TYPE_LABELS_V1, row$asset_type), Quantity=pl_quantity_v1(row$remaining_quantity_decimal, "—"))
      else list(Account=row$account_selection_label, Quantity=pl_quantity_v1(row$remaining_quantity_decimal, "—"),
        `Im Formular`=if (identical(row$account_ref, marked)) "\u2713 gewählt" else "")
    )), recursive=FALSE)
    activity_german_frame(desktop_workflow_rows_frame_v1(rows))
  }
  # Gegenprobe (rc.335): Die Konten zusammen ergeben exakt den Bestand des Assets. Gerechnet mit exakten Dezimalen, nie als Zahl.
  activity_custody_check <- function(projection) {
    if (is.null(projection) || !identical(projection$status, "ready")) return(NULL)
    parse <- function(value) tryCatch(.transaction_decimal_parse(as.character(value)), error = function(error) NULL)
    total <- .transaction_decimal_zero(); parts <- .transaction_decimal_zero(); accounts <- 0L
    for (portfolio in projection$portfolios) {
      for (row in portfolio$positions) { value <- parse(row$remaining_quantity_decimal); if (is.null(value)) return(NULL); total <- .transaction_decimal_add(total, value) }
      for (row in portfolio$custody_positions) { value <- parse(row$remaining_quantity_decimal); if (is.null(value)) return(NULL); parts <- .transaction_decimal_add(parts, value); accounts <- accounts + 1L }
    }
    if (.transaction_decimal_equal(total, parts))
      return(shiny::p(class = "pl-field-hint", sprintf("Gegenprobe: %d %s zusammen = Bestand oben (%s).", accounts,
        if (accounts == 1L) "Konto" else "Konten", .transaction_decimal_string(total))))
    portelyra_status_panel("Konten ergeben nicht den Bestand", paste0("Summe der Konten ", .transaction_decimal_string(parts),
      ", Bestand oben ", .transaction_decimal_string(total), ". Bitte die Buchungen dieses Assets prüfen."), tone = "warning")
  }
  output$activity_custody_positions <- shiny::renderTable(activity_custody_frame(activity_selection_projection()),striped=TRUE,bordered=TRUE)
  output$activity_context_custody_positions <- shiny::renderTable({
    marked <- input$activity_account
    activity_custody_frame(activity_context_projection(), marked = if (is.character(marked) && length(marked) == 1L && !is.na(marked)) marked else "")
  },striped=TRUE,bordered=TRUE)
  output$activity_context_custody_check <- shiny::renderUI(activity_custody_check(activity_context_projection()))
  activity_history_focus <- function() {
    focus <- input$activity_asset
    if (is.character(focus) && length(focus) == 1L && !is.na(focus) && nzchar(focus)) focus else NULL
  }
  activity_history_events <- function(portfolio) {
    focus <- activity_history_focus()
    if (is.null(focus)) return(portfolio$events_newest_first)
    Filter(function(row) identical(row$asset_ref, focus), portfolio$events_newest_first)
  }
  output$activity_history_scope <- shiny::renderUI({
    focus <- activity_history_focus(); projection <- activity_selection_projection()
    if (is.null(focus) || is.null(projection) || !projection$status %in% c("ready", "empty")) return(NULL)
    count <- sum(vapply(projection$portfolios, function(portfolio) length(activity_history_events(portfolio)), integer(1L)))
    catalog <- activity_catalog()
    asset <- if (is.null(catalog)) list() else Filter(function(row) identical(row$ref, focus), catalog$assets)
    label <- if (length(asset)) (if (!is.null(asset[[1L]]$selection_label)) asset[[1L]]$selection_label else asset[[1L]]$label) else "gewähltes Asset"
    portelyra_status_panel(
      paste("Asset-Historie für", label),
      if (count) paste(count, "Ereignis(se) im gewählten Zeitraum, neueste zuerst. Ohne Asset im Formular erscheinen alle Assets.")
      else "Für dieses Asset gibt es im gewählten Zeitraum keine Ereignisse. Ohne Asset im Formular erscheinen alle Assets.",
      tone = "neutral")
  })
  # Der Arbeitskontext, lesbar statt bedienbar: Asset und Portfolio kommen aus
  # der Suche des Asset-Centers. Weicht das Formular davon ab, steht es hier
  # ausdruecklich - stillschweigend auseinanderlaufen duerfen die beiden nicht,
  # genau das war der Fehler von rc.222/rc.223 (#424).
  output$activity_target_context <- shiny::renderUI({
    model <- activity_catalog()
    label <- function(area, ref) {
      if (is.null(model) || !is.character(ref) || length(ref) != 1L || !nzchar(ref)) return(NULL)
      treffer <- Filter(function(row) identical(row$ref, ref), model[[area]])
      if (length(treffer) == 1L) treffer[[1L]]$label else NULL
    }
    asset <- label("assets", input$activity_asset)
    portfolio <- label("portfolios", input$activity_portfolio)
    gesucht <- tryCatch({
      katalog <- asset_center_catalog()
      treffer <- if (is.null(katalog) || !nzchar(as.character(input$asset_center_asset))) NULL
        else data_asset_center_selected_v1(katalog, input$asset_center_asset)
      if (is.null(treffer)) NULL else treffer$display_name
    }, error = function(error) NULL)
    if (is.null(asset)) return(portelyra_status_panel(
      "Kein Asset im Arbeitskontext",
      "Das Asset kommt aus der Suche über den Reitern. Dort eines wählen; Portfolio und Asset sind im Formular nicht mehr einstellbar.",
      tone = "neutral"))
    abweichend <- !is.null(gesucht) && !startsWith(asset, gesucht)
    portelyra_status_panel(
      paste("Arbeitskontext ·", asset),
      paste0(if (is.null(portfolio)) "Portfolio noch offen" else paste("Portfolio", portfolio),
        " · Das Asset kommt aus der Suche, nicht aus dem Formular.",
        if (abweichend) paste0(" Die Suche steht auf ", gesucht,
          "; die Übernahme ist gesperrt, solange Beträge eingegeben oder Buchungen ausgewählt sind.") else ""),
      tone = if (abweichend) "warning" else "neutral")
  })
  # Stand und Bericht der Sammelbearbeitung (#424).
  output$activity_sequence_mode <- shiny::renderText({
    if (!is.null(activity_sequence())) "running"
    else if (length(workflow_refs()) > 1L) "offer"
    else "off"
  })
  shiny::outputOptions(output, "activity_sequence_mode", suspendWhenHidden = FALSE)
  output$activity_sequence_state <- shiny::renderUI({
    reihe <- activity_sequence()
    if (is.null(reihe)) return(NULL)
    daten <- activity_rows_frame()
    ref <- activity_sequence_ref()
    beschreibung <- if (!length(ref) || is.null(daten)) NULL else {
      treffer <- which(daten$keys == ref)
      if (!length(treffer)) NULL else paste(
        pl_day_v1(daten$frame$Datum[[treffer[[1L]]]]), "·", daten$frame$Art[[treffer[[1L]]]], "·",
        daten$frame$Konto[[treffer[[1L]]]], "· Menge", pl_quantity_v1(daten$frame$Menge[[treffer[[1L]]]]))
    }
    gezaehlt <- function(wert) sum(reihe$outcomes == wert)
    portelyra_status_panel(
      sprintf("Durchgang · Buchung %d von %d", reihe$index, length(reihe$keys)),
      paste0(if (is.null(beschreibung)) "Diese Buchung ist in der Tabelle gewählt." else beschreibung,
        " · bisher ", gezaehlt("corrected"), " geändert, ", gezaehlt("voided"), " storniert, ",
        gezaehlt("unchanged"), " unverändert.",
        " Ändern und bestätigen, stornieren oder unverändert lassen."),
      tone = "warning")
  })
  output$activity_sequence_report <- shiny::renderUI({
    bericht <- activity_sequence_report()
    if (is.null(bericht)) return(NULL)
    gezaehlt <- function(wert) sum(bericht$outcomes == wert)
    titel <- switch(bericht$status,
      finished = "Durchgang abgeschlossen",
      stopped = "Durchgang beendet",
      broken = "Durchgang abgebrochen")
    kopie <- paste0(length(bericht$outcomes), " von ", bericht$total, " Buchungen durchgegangen · ",
      gezaehlt("corrected"), " geändert, ", gezaehlt("voided"), " storniert, ",
      gezaehlt("unchanged"), " unverändert.")
    if (identical(bericht$status, "broken")) kopie <- paste(kopie,
      "Die restlichen Buchungen ließen sich nach der letzten Änderung nicht mehr eindeutig zuordnen.",
      "Geschriebene Änderungen bleiben; für die übrigen die Auswahl neu treffen.")
    portelyra_status_panel(titel, kopie,
      tone = if (identical(bericht$status, "finished")) "positive" else "warning")
  })
  # Filter, Tabelle und Hinweis der Buchungsauswahl (#424).
  output$activity_rows_filter <- shiny::renderUI({
    daten <- activity_rows_frame()
    if (is.null(daten)) return(NULL)
    data_table_workbench_filter_ui_v1("activity_rows", daten$frame, activity_rows_columns())
  })
  output$activity_rows_table <- shiny::renderUI({
    daten <- activity_rows_frame()
    # Zwei verschiedene Auskuenfte: Die Liste liess sich nicht lesen, oder es gibt
    # noch keine Buchung. Seit die Liste von selbst laedt, ist das erste die Ausnahme.
    if (is.null(daten)) return(shiny::p(class="pl-field-hint",
      if (is.null(correction_model())) "Die Buchungen sind noch nicht gelesen. \u201eBuchungen neu lesen\u201c holt sie."
      else "Es gibt noch keine Buchungen."))
    zeilen <- data_table_workbench_rows_v1("activity_rows", daten$frame, activity_rows_columns(), input)
    # Ohne gewaehltes Asset (Start seit rc.332): die neuesten Buchungen aller Assets, nicht tausende Zeilen. Die Spaltenfilter
    # wirken auf alle; gezeigt werden die ersten ACTIVITY_ROWS_ALL_LIMIT der (nach Datum absteigend sortierten) Treffer.
    gefiltert <- length(zeilen)
    if (is.null(daten$asset) && gefiltert > ACTIVITY_ROWS_ALL_LIMIT) zeilen <- zeilen[seq_len(ACTIVITY_ROWS_ALL_LIMIT)]
    shiny::tagList(
      shiny::p(class="pl-field-hint", if (is.null(daten$asset))
        paste0("Alle Assets · ", if (gefiltert > length(zeilen)) sprintf("die %d neuesten von %d Buchungen. ", length(zeilen), gefiltert)
               else sprintf("%d Buchungen. ", gefiltert), "Ein Asset oben wählen oder filtern, um gezielt zu suchen.")
        else sprintf("Buchungen von %s · %d.", daten$asset, gefiltert)),
      data_table_workbench_table_v1("activity_rows", daten$frame[zeilen,,drop=FALSE],
        activity_rows_columns(), daten$keys[zeilen], selected=workflow_refs(),
        empty=if (is.null(daten$asset)) "Keine Buchung passt zum Filter."
          else sprintf("Keine Buchung für %s%s.", daten$asset,
            if (nrow(daten$frame)>0L) " passt zum Filter" else "")))
  })
  output$activity_reference_panel <- shiny::renderUI({
    ziel <- activity_reference_target()
    if (is.null(ziel)) return(NULL)
    belege <- activity_reference_model()
    stand <- belege[[as.character(ziel$event_ref)]]
    feld <- function(name) { wert <- data_activity_reference_text_v1(stand[[name]]); if (is.null(wert)) "" else wert }
    abgang <- identical(ziel$event_type, "withdrawal")
    werte <- if (abgang) activity_value_model() else list()
    wert <- if (abgang) werte[[as.character(ziel$event_ref)]] else NULL
    shiny::tags$details(class="pl-disclosure", open=if (is.list(stand) || is.list(wert)) "open" else NULL,
      shiny::tags$summary(if (abgang) "Beleg zur gewählten Buchung · Transaktions-ID, Adresse, Notiz, Wert des Abgangs"
        else "Beleg zur gewählten Buchung · Transaktions-ID, Adresse, Notiz"),
      shiny::p(class="pl-section-copy",
        "Die Angaben dokumentieren die Buchung. Bestand, FIFO und Bewertung ändern sich dadurch nicht."),
      if (isTRUE(attr(belege, "unreadable"))) portelyra_status_panel("Belegangaben nicht lesbar",
        "Der Speicher der Belegangaben ließ sich nicht lesen. Die Buchungen selbst sind davon nicht berührt.", tone="warning"),
      shiny::textInput("activity_reference_transaction_id", "Transaktions-ID (Order-ID der Börse oder Transaktions-Hash)", value=feld("transaction_id")),
      shiny::textInput("activity_reference_address", "Wallet-Adresse oder Public Key der Gegenseite", value=feld("counterparty_address")),
      shiny::textAreaInput("activity_reference_note", "Notiz", value=feld("note"), rows=2),
      if (is.list(stand)) shiny::p(class="pl-field-hint", paste0("Stand: ", data_activity_reference_origin_label_v1(stand$origin), ".")),
      if (abgang) shiny::tagList(
        if (isTRUE(attr(werte, "unreadable"))) portelyra_status_panel("Wert des Abgangs nicht lesbar",
          "Der Speicher der eingetragenen Werte ließ sich nicht lesen. Die Buchungen selbst sind davon nicht berührt.", tone="warning"),
        shiny::textInput("activity_reference_value", "Wert des Abgangs in EUR", value=data_activity_reference_value_label_v1(wert$value_eur_decimal),
          placeholder="z. B. 25,50"),
        shiny::p(class="pl-field-hint", paste0(
          "Wieviel abgegangen ist – unabhängig von der steuerlichen Einordnung. Bleibt das Feld leer, setzt der Steuerreport ",
          "Stückzahl mal Tageskurs der Kursquelle am Tag des Abgangs an.",
          if (is.list(wert)) paste0(" Wert: ", data_activity_reference_origin_label_v1(wert$origin), ".") else ""))),
      shiny::div(class="pl-editor-actions", shiny::actionButton("activity_reference_save", "Beleg speichern", class="btn-primary")),
      # Die Meldung ist eine eigene Ausgabe: Nach einer abgewiesenen Eingabe wird
      # der Bereich nicht neu aufgebaut, das Getippte bleibt stehen.
      shiny::uiOutput("activity_reference_notice"))
  })
  output$activity_reference_notice <- shiny::renderUI({
    meldung <- activity_reference_notice()
    if (is.list(meldung)) portelyra_status_panel(meldung$title, meldung$copy, tone=meldung$tone)
  })
  # Wechselt die Auswahl, gehoert die Meldung des letzten Speicherns nicht mehr zur gezeigten Buchung.
  shiny::observeEvent(input$activity_rows_selected, activity_reference_notice(NULL), ignoreNULL=FALSE, ignoreInit=TRUE)
  shiny::observeEvent(input$activity_reference_save, {
    ziel <- activity_reference_target()
    if (is.null(ziel)) return(invisible(NULL))
    abgang <- identical(ziel$event_type, "withdrawal")
    # Der Wert wird vor dem ersten Schreiben geprueft: Eine abgewiesene Eingabe speichert auch die uebrigen Angaben nicht.
    betrag <- if (abgang) data_activity_reference_value_v1(input$activity_reference_value) else NULL
    if (!is.null(betrag) && is.na(betrag)) {
      activity_reference_notice(list(title="Beleg nicht gespeichert", tone="error",
        copy="Der Wert des Abgangs ist ein Betrag in EUR ohne Vorzeichen und ohne Tausendertrenner, zum Beispiel 25,50. Ein leeres Feld heißt: kein eingetragener Wert."))
      return(invisible(NULL))
    }
    jetzt <- format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz="UTC")
    ergebnis <- tryCatch(activity_reference_service$record(as.character(ziel$event_ref), input$activity_reference_transaction_id,
        input$activity_reference_address, input$activity_reference_note, jetzt, TRUE),
      spot_data_activity_reference_error_v1=function(error) error$code, error=function(error) "activity_reference_store_invalid")
    wertergebnis <- if (!abgang || !is.list(ergebnis)) NULL else tryCatch(
      activity_reference_service$record_value(as.character(ziel$event_ref), input$activity_reference_value, jetzt, TRUE),
      spot_data_activity_reference_error_v1=function(error) error$code, error=function(error) "activity_reference_store_invalid")
    if (is.list(ergebnis) && (is.null(wertergebnis) || is.list(wertergebnis))) {
      geschrieben <- as.integer(ergebnis$written_count) + if (is.list(wertergebnis)) as.integer(wertergebnis$written_count) else 0L
      activity_reference_notice(list(title=if (identical(geschrieben, 0L)) "Nichts geändert" else "Beleg gespeichert",
        copy=if (identical(geschrieben, 0L)) "Die Angaben stimmen mit dem gespeicherten Stand überein."
          else "Die Angaben stehen jetzt an dieser Buchung.", tone="positive"))
      activity_reference_tick(activity_reference_tick() + 1L)
    } else if (is.list(ergebnis)) {
      # Die Belegangaben sind gespeichert, der Wert nicht: beides wird genannt.
      activity_reference_notice(list(title="Wert des Abgangs nicht gespeichert", tone="error", copy=paste(
        "Transaktions-ID, Adresse und Notiz sind gespeichert.", switch(wertergebnis,
          activity_reference_value_not_applicable="Ein Wert lässt sich nur an einem Abgang eintragen.",
          activity_reference_event_unknown="Diese Buchung gibt es im Bestand nicht mehr. Bitte die Buchungen neu lesen.",
          "Der Speicher der eingetragenen Werte ließ sich nicht schreiben."))))
      activity_reference_tick(activity_reference_tick() + 1L)
    } else {
      activity_reference_notice(list(title="Beleg nicht gespeichert", tone="error", copy=switch(ergebnis,
        activity_reference_input_invalid="Transaktions-ID und Adresse sind eine zusammenhängende Zeichenfolge ohne Leerzeichen (höchstens 200 Zeichen). Freitext gehört in die Notiz.",
        activity_reference_event_unknown="Diese Buchung gibt es im Bestand nicht mehr. Bitte die Buchungen neu lesen.",
        "Der Speicher der Belegangaben ließ sich nicht schreiben.")))
    }
  })
  output$activity_rows_hint <- shiny::renderUI({
    daten <- activity_rows_frame()
    if (is.null(daten)) return(NULL)
    zeilen <- data_table_workbench_rows_v1("activity_rows", daten$frame, activity_rows_columns(), input)
    hinweis <- data_table_workbench_selection_hint_v1(workflow_refs(), nrow(daten$frame), length(zeilen))
    titel <- if (is.null(daten$asset)) hinweis$title else paste0(daten$asset, " · ", hinweis$title)
    portelyra_status_panel(titel, hinweis$copy, tone=hinweis$tone)
  })
  output$activity_history <- shiny::renderTable({
    projection <- activity_selection_projection()
    if (is.null(projection) || !projection$status %in% c("ready", "empty")) return(data.frame())
    rows <- unlist(lapply(projection$portfolios, function(portfolio) lapply(activity_history_events(portfolio), function(row) list(
      Portfolio=portfolio$portfolio_label, Date=pl_day_v1(row$local_date),
      Time=if (is.null(row$effective_at_utc)) "nur Datum" else pl_moment_v1(row$effective_at_utc),
      Event=pl_label_v1(PL_EVENT_TYPE_LABELS_V1, row$event_type), Account=row$account_selection_label,
      Related_Account=if (is.null(row$related_account_selection_label)) "—" else row$related_account_selection_label,
      Asset=row$asset_selection_label, Asset_Type=pl_label_v1(PL_ASSET_TYPE_LABELS_V1, row$asset_type),
      Quantity=pl_quantity_v1(row$quantity_decimal, "—"), Amount=activity_money(row$amount_decimal, row$currency),
      FIFO_Basis_Added=activity_money(row$basis_added, row$currency), FIFO_Basis_Consumed=activity_money(row$basis_consumed, row$currency),
      Proceeds=activity_money(row$gross_proceeds_decimal, row$currency), Realized_GuV=activity_money(row$realized_gain, row$currency),
      Income=activity_money(row$gross_income_decimal, row$currency), Cash_Delta=activity_money(row$cash_balance_delta_decimal, row$currency),
      # Vertrag, FIFO-Grundlage, Berechnungsstand und automatisches Cash sind Kennungen des Kerns ohne Aussage fuer den
      # Eigentuemer; sie stehen seit #490 nicht mehr in der Tabelle.
      Calculation_Status=pl_label_v1(c(fresh_completed="aktuell", stale="veraltet", pending="steht aus", failed="fehlgeschlagen"), row$calculation_status)
    ))), recursive=FALSE)
    activity_german_frame(desktop_workflow_rows_frame_v1(rows))
  }, striped=TRUE, bordered=TRUE)
  output$activity_preview <- shiny::renderTable({
    preview <- activity_preview(); if (is.null(preview)) return(data.frame())
    data.frame(
      Feld=c("Ereignis", "Datum", "Uhrzeit", "Zeitzone", "UTC", "Bestandswirkung", "FIFO", "Mengenänderung", "FIFO-Basis neu", "FIFO-Basis verbraucht", "Nettoerlös", "Realisierte GuV", "Ertrag", "Durchschnittskosten", "Cash-Wirkung", "Cash-Buchungszeilen"),
      # Auf Deutsch (0.3.4, #578): Art, Tag und Wirkung mit Namen, Mengen und Betraege wie in der Buchungstabelle (ohne Einheit; die
      # Vorschau nennt keine Waehrung). Mit „Exakte Brüche anzeigen“ bleiben die Werte, wie der Kern sie fuehrt.
      Wert=c(desktop_activity_event_label_v1(preview$event_type), pl_day_v1(preview$local_date), if (is.null(preview$local_time)) "—" else preview$local_time,
             preview$time_zone, if (is.null(preview$effective_at_utc)) "—" else activity_utc_text(preview$effective_at_utc),
             pl_label_v1(DESKTOP_ACTIVITY_INVENTORY_EFFECT_LABELS_V1, preview$inventory_effect_code),
             pl_label_v1(DESKTOP_ACTIVITY_FIFO_EFFECT_LABELS_V1, preview$fifo_effect_code),
             if (isTRUE(input$activity_show_exact_ratios)) preview$portfolio_quantity_change_decimal else pl_quantity_v1(preview$portfolio_quantity_change_decimal),
             activity_money(preview$fifo_basis_created_decimal, ""),
             activity_money(preview$consumed_fifo_basis_display, ""),
             activity_money(preview$net_trade_proceeds_decimal, ""),
             activity_money(preview$realized_gross_gain_display, ""),
             activity_money(preview$gross_income_decimal, ""),
             activity_price(preview$cost_average_display, ""),
             activity_money(preview$cash_balance_delta_decimal, ""), "0"), check.names=FALSE
    )
  }, striped=TRUE, bordered=TRUE)
  # Steuert die Sichtbarkeit der Skalenfelder. Eine eigene Ausgabe statt einer
  # JS-Bedingung auf die Warnung selbst: Die Warnung ist renderUI, ihr Textinhalt
  # ist fuer conditionalPanel keine verlaessliche Bedingung.
  output$activity_scale_state <- shiny::renderText(if (is.null(scale_preview())) "none" else "warned")
  shiny::outputOptions(output, "activity_scale_state", suspendWhenHidden = FALSE)
  output$activity_scale_warning <- shiny::renderUI({
    preview <- scale_preview()
    if (is.null(preview)) return(NULL)
    portelyra_status_panel(
      paste("Mengenskala", preview$current_quantity_scale, "→", preview$proposed_quantity_scale),
      paste(preview$warning_text, "Betroffene FIFO-Welten:", preview$affected_fifo_world_count),
      tone = "warning"
    )
  })
  output$activity_correction_state <- shiny::renderUI({
    model<-correction_model();preview<-correction_preview();if(is.null(model))return(portelyra_status_panel("Korrekturauswahl nicht geladen","Lesen öffnet keine Quelle und schreibt nichts."))
    portelyra_status_panel(if(is.null(preview))"Generation-Korrektur bereit"else"Supersession wartet auf Bestätigung",paste(length(model$candidates),"aktive Vorgänger ·",model$history$correction_count,"bisherige Korrekturen/Stornos"),tone=if(is.null(preview))"neutral"else"warning")
  })
  output$activity_batch_review <- shiny::renderUI(data_asset_activity_batch_review_ui_v2(correction_preview()))
  output$activity_draft_batch_review <- shiny::renderUI({model<-activity_draft_open();if(is.null(model))return(NULL);data_asset_activity_batch_review_ui_v2(model$batch_preview)})
  output$activity_correction_preview <- shiny::renderTable({
    preview<-correction_preview();if(is.null(preview))return(data.frame())
    if(!is.null(preview$selected_event_count))return(data.frame(Feld=c('Aktion','Ausgewählte Buchungen','Betroffene FIFO-Welten','Historische Generationen','Cash'),Wert=c('Gemeinsames Storno',preview$selected_event_count,preview$affected_fifo_world_count,'bleiben erhalten','unverändert'),check.names=FALSE))
    replacement<-preview$replacement
    after<-if(identical(preview$after_state,'no_remaining_events'))'keine verbleibenden Ereignisse'else'FIFO-Welt bleibt vorhanden'
    data.frame(Feld=c('Aktion','Vorgänger-Ereignis','Vorgänger-Menge','Ersatz-Bestandswirkung','Ersatz-FIFO','Betroffene FIFO-Welten','Zustand danach','Vorgänger erhalten','Cash-Buchungszeilen'),
      Wert=c(preview$action_type,preview$predecessor$event_type,if(is.null(preview$predecessor$quantity_decimal))'—'else preview$predecessor$quantity_decimal,if(is.null(replacement))'entfällt'else replacement$inventory_effect_code,if(is.null(replacement))'entfällt'else replacement$fifo_effect_code,preview$affected_fifo_world_count,after,'ja','0'),check.names=FALSE)
  },striped=TRUE,bordered=TRUE)
  shiny::observeEvent(input$activity_correction_history_clear, correction_history_hidden(TRUE), ignoreInit=TRUE)
  shiny::observeEvent(input$activity_correction_history_show, correction_history_hidden(FALSE), ignoreInit=TRUE)
  output$activity_correction_history_state <- shiny::renderUI({
    model <- correction_model()
    count <- if (is.null(model) || is.null(model$history$rows)) 0L else length(model$history$rows)
    if (isTRUE(correction_history_hidden())) return(portelyra_status_panel(
      "Anzeige geleert",
      paste0(count, " Generationsbeleg(e) bleiben unveraendert erhalten und sind nicht geloescht. Mit \u201eAnzeige wieder einblenden\u201c erscheinen sie erneut."),
      tone="neutral"))
    # Ein Beleg aus einem fremden Kontext wird nicht verschwiegen. Er sperrt die
    # Historie seit rc.222 nicht mehr, aber dass er da ist, soll man sehen - er
    # bedeutet, dass eine Korrektur mit falsch gebildetem Akteur geschrieben wurde
    # (#424).
    fremd <- if (is.null(model)) 0L else as.integer(model$history$foreign_receipt_count)
    if (!is.na(fremd) && fremd > 0L) return(portelyra_status_panel(
      sprintf("%d Generationsbeleg%s aus fremdem Kontext", fremd, if(fremd==1L)"" else "e"),
      paste0("Die eigene Korrekturhistorie ist vollständig lesbar (", count,
             " Einträge). Der fremde Beleg bleibt unverändert erhalten; seine Buchungen sind wirksam.",
             " Er stammt von einem Schreibvorgang, dessen Akteurskennung abweicht."),
      tone="warning"))
    NULL
  })
  # Bewusst kein Observer auf die Asset-Center-Auswahl: Ein dort gesetztes
  # activity_asset laesst den Handoff einen begonnenen Entwurf vermuten und
  # verweigert sich. Die Vorbelegung erfolgt stattdessen in
  # refresh_activity_catalog(), also beim ausdruecklichen Aktualisieren.
  output$activity_context_block <- shiny::renderUI({
    reason <- activity_context_block()
    if (is.null(reason)) return(NULL)
    portelyra_status_panel("Arbeitskontext nicht übernommen", reason, tone = "warning")
  })
  shiny::observeEvent(input$activity_draft_discard, {
    if (length(workflow_refs())) {
      state(list(tone = "warning", title = "Nichts verworfen",
        copy = "Eine Buchung ist ausgewählt. Sie wird über die Buchungsauswahl aufgehoben, nicht über diesen Button."))
      return()
    }
    # Verworfen wird ausschliesslich der nicht gespeicherte Formularzustand:
    # keine Buchung, kein persistenter Draft, keine Generation.
    # Der Steuersatz der Netto-Umrechnung bleibt stehen: Er gilt meist fuer die
    # naechste Dividende wieder; geleert werden die Betraege.
    for (field in c("activity_quantity", "activity_unit_price", "activity_gross_total",
                    "activity_net_total", "activity_net_unit_price",
                    "activity_monetary_fee", "activity_asset_fee",
                    "activity_eligible_quantity", "activity_provided_basis")) {
      shiny::updateTextInput(session, field, value = "")
    }
    activity_preview(NULL); activity_approval(NULL); activity_completed(NULL)
    action_feedback$clear("activity")
    safe(refresh_activity_catalog(force_context = TRUE), function(model) {
      state(list(tone = "neutral", title = "Eingaben verworfen",
        copy = "Die eingegebenen Beträge sind geleert und der Arbeitskontext aus dem Asset-Center ist übernommen. Es wurde nichts gespeichert oder gebucht."))
    })
  }, ignoreInit = TRUE)
  output$activity_correction_history <- shiny::renderTable({model<-correction_model();if(isTRUE(correction_history_hidden())||is.null(model)||!length(model$history$rows))return(data.frame());desktop_workflow_rows_frame_v1(lapply(model$history$rows,function(row)list(Aktion=if(identical(row$action_type,'void'))'Storno'else'Korrektur',Buchungen=if(is.null(row$selected_event_count))1L else row$selected_event_count,Gespeichert=pl_moment_v1(row$committed_at_utc),Ersatzbuchungen=row$replacement_event_count,`Historie erhalten`='ja')))},striped=TRUE,bordered=TRUE)
  output$portfolio_completion_status<-shiny::renderUI({
    notice<-portfolio_completion_notice();model<-realized_model()
    if(is.list(notice)&&identical(notice$status,"update_required"))return(portelyra_status_panel("Rechenstand wartet aufs Nachrechnen",paste(notice$committed_count,"neue Buchungen · erst prüfen, dann nachrechnen"),tone="warning"))
    if(is.null(model))return(portelyra_status_panel("Rechenstand noch nicht geprüft","„Rechenstand prüfen“ liest nur und rechnet nichts."))
    # Ohne Rechnung (noch keine Buchung) liegt nichts zurueck; ein fehlgeschlagener Lauf ist etwas anderes als ein offener.
    if(identical(model$freshness,"unavailable"))return(portelyra_status_panel("Noch nichts gerechnet","Die Rechnung entsteht mit der ersten Buchung; „Nachrechnen“ legt sie auch von Hand an."))
    if(identical(model$freshness,"stale_failed"))return(portelyra_status_panel("Letzte Rechnung fehlgeschlagen",paste(model$world_count,"gerechnete Assets · „Nachrechnen“ versucht es erneut"),tone="warning"))
    if(identical(model$freshness,"stale_pending"))return(portelyra_status_panel("Rechnung steht aus",paste(model$world_count,"gerechnete Assets · ein begonnener Lauf ist nicht abgeschlossen; läuft keiner mehr, rechnet „Nachrechnen“ neu"),tone="warning"))
    if(!identical(model$freshness,"fresh"))return(portelyra_status_panel("Rechenstand liegt zurück",paste(model$world_count,"gerechnete Assets · „Nachrechnen“ bringt sie auf den Stand der Buchungen"),tone="warning"))
    portelyra_status_panel("Rechenstand aktuell",paste(model$world_count,"gerechnete Assets ·",model$changed_world_count,"zuletzt neu gerechnet · Bestand und Buchungen lassen sich unten ansehen"),tone="positive")
  })
  output$portfolio_completion_positions<-shiny::renderTable({
    view<-activity_read_view();selected<-input$portfolio_completion_assets
    if(is.null(view)||!identical(view$fifo_state,"fresh")||is.null(selected)||!length(selected))return(data.frame())
    rows<-unlist(lapply(view$portfolios,function(portfolio)lapply(Filter(function(row)row$asset_ref%in%selected,portfolio$positions),function(row)list(Portfolio=portfolio$portfolio_label,Asset=row$asset_label,Menge=row$remaining_quantity_decimal,Einstandswert=activity_exact_display(row$remaining_fifo_basis),`Ø Einstandskurs`=activity_exact_display(row$cost_average),Ertrag=activity_exact_display(row$gross_income)))),recursive=FALSE)
    desktop_workflow_rows_frame_v1(rows)
  },striped=TRUE,bordered=TRUE)
  output$portfolio_completion_history<-shiny::renderTable({
    view<-activity_read_view();selected<-input$portfolio_completion_assets
    if(is.null(view)||is.null(selected)||!length(selected))return(data.frame())
    rows<-unlist(lapply(view$portfolios,function(portfolio)lapply(Filter(function(row)row$asset_ref%in%selected,portfolio$events_newest_first),function(row)list(Portfolio=portfolio$portfolio_label,Datum=row$local_date,Buchungsart=activity_event_label(row$event_type),Konto=row$account_label,Asset=row$asset_label,Menge=row$quantity_decimal,Betrag=row$amount_decimal,Ertrag=row$gross_income_decimal,Rechenstatus=row$calculation_status))),recursive=FALSE)
    desktop_workflow_rows_frame_v1(rows)
  },striped=TRUE,bordered=TRUE)
  output$realized_state_status <- shiny::renderUI({model<-realized_model();parity<-realized_parity();if(is.null(model))return(portelyra_status_panel("Rechenstand nicht gelesen","„Rechenstand prüfen“ oben liest ihn. Gibt es noch keinen, einmal „Komplett neu rechnen“."));portelyra_status_panel(paste("Rechenstand",realized_freshness_label(model$freshness)),paste(model$world_count,"gerechnete Assets · zuletzt komplett neu gerechnet und bestätigt:",if(isTRUE(model$full_rebuild_verified))"ja"else"nein","· Vollständigkeit:",model$portfolio_completeness,if(is.null(parity))""else"· Gegenprüfung: genau gleich"),tone=if(identical(model$freshness,"fresh"))"neutral"else"warning")})
  output$realized_state_dimensions <- shiny::renderTable({model<-readiness_model();if(is.null(model)||!length(model$dimensions))return(data.frame());portelyra_readiness_frame_v1(model)},striped=TRUE,bordered=TRUE)
  # Eine Zeile vor der Tabelle: belastbar oder nicht, und woran es liegt (#189).
  output$portfolio_readiness_panel <- shiny::renderUI({
    model <- readiness_model()
    if (is.null(model)) return(NULL)
    portelyra_status_panel(if (isTRUE(model$market_valuation_ready)) "Bewertung belastbar" else "Bewertung noch nicht belastbar",
      portelyra_readiness_headline_v1(model), tone = if (isTRUE(model$market_valuation_ready)) "positive" else "warning")
  })
  realized_asset_presentation <- function(rows) {
    catalog <- activity_catalog()
    selection <- tryCatch(.data_asset_activity_selection(activity_editor, runtime$context), error=function(error) NULL)
    label_by_ref <- if (is.null(catalog) || !length(catalog$assets)) character() else stats::setNames(
      vapply(catalog$assets, function(asset) if (!is.null(asset$selection_label)) asset$selection_label else asset$label, character(1L)),
      vapply(catalog$assets, `[[`, character(1L), "ref")
    )
    lapply(rows, function(row) {
      editor_ref <- if (is.null(selection) || is.null(row$asset_ref)) NULL else unname(selection$assets$ref_by_id[[row$asset_ref]])
      row$asset_ref <- NULL
      label <- if (is.null(editor_ref)) NULL else unname(label_by_ref[[editor_ref]])
      c(list(Asset=if (is.null(label) || !nzchar(label)) "nicht zuordenbar" else label), row)
    })
  }
  # Seit rc.331 steht die Tabelle unter "Bestand pruefen" und folgt der Auswahl "Assets ansehen" dort, nicht mehr dem
  # Formular in "Manuell".
  realized_positions_for_selected_assets <- function(rows) {
    # Bewusst nicht isoliert: Einzige Aufrufstelle ist output$realized_state_positions,
    # also immer ein reaktiver Kontext. Mit isolate() hing die Tabelle nicht von der
    # Auswahl ab und rendert nur bei geaendertem Modell neu.
    focus <- input$portfolio_completion_assets
    focus <- if (is.character(focus)) focus[!is.na(focus) & nzchar(focus)] else character()
    if (!length(focus)) return(rows)
    selection <- tryCatch(.data_asset_activity_selection(activity_editor, runtime$context), error=function(error) NULL)
    if (is.null(selection)) return(rows)
    matched <- Filter(function(row) {
      if (is.null(row$asset_ref)) return(FALSE)
      ref <- unname(selection$assets$ref_by_id[[row$asset_ref]])
      length(ref) == 1L && ref %in% focus
    }, rows)
    # Ohne Treffer bleibt die vollstaendige Liste stehen statt faelschlich leer
    # zu wirken: Ein leeres Ergebnis waere von "keine Positionen" ununterscheidbar.
    if (!length(matched)) rows else matched
  }
  output$realized_state_positions <- shiny::renderTable({
    model<-realized_model();if(is.null(model)||!length(model$positions))return(data.frame())
    exact_fields<-c("remaining_fifo_basis","cost_average","realized_gross_proceeds","realized_fifo_basis","realized_gain_before_tax","gross_income","monetary_fees")
    positions<-lapply(realized_positions_for_selected_assets(model$positions),function(row){for(field in exact_fields)if(!is.null(row[[field]]))row[[field]]<-activity_exact_display(row[[field]]);row})
    desktop_workflow_rows_frame_v1(realized_asset_presentation(positions))
  },striped=TRUE,bordered=TRUE)
  output$activity_quick_state <- shiny::renderUI({inspection<-activity_quick_inspection();prepared<-activity_quick_prepared();if(is.null(inspection))return(portelyra_status_panel("Schnellimport nicht geprüft","Gebucht wird als Eigentümer."));if(is.null(prepared))return(portelyra_status_panel(paste("Tolerante Datei",inspection$status),paste(inspection$activity_row_count,"Zeilen mit Buchungen ·",inspection$asset_only_row_count,"nur Asset"),tone=if(inspection$blocked_row_count)"error"else if(inspection$needs_input_row_count)"warning"else"neutral"));portelyra_status_panel("Buchungsentwürfe vorbereitet",paste(prepared$ready_row_count,"bereit ·",prepared$needs_input_row_count,"Angaben fehlen ·",prepared$blocked_row_count,"blockiert ·",prepared$applying_row_count,"in Wiederaufnahme ·",prepared$already_committed_draft_count,"bereits gebunden · Entwürfe neu/wiederverwendet",paste0(prepared$created_draft_count,"/",prepared$reused_draft_count)),tone=if(prepared$applying_row_count||prepared$blocked_row_count)"error"else if(prepared$needs_input_row_count)"warning"else"neutral")})
  output$activity_quick_rows <- shiny::renderTable({model<-activity_quick_prepared();if(is.null(model)||!length(model$rows))return(data.frame());desktop_workflow_rows_frame_v1(model$rows)},striped=TRUE,bordered=TRUE)
  output$activity_quick_mapping_ui <- shiny::renderUI({
    model<-activity_quick_inspection();catalog<-activity_catalog();if(is.null(model)||is.null(catalog)||!is.list(model$mapping_requirements))return(NULL)
    make<-function(kind,singular,choices,default_ref){requirements<-model$mapping_requirements[[kind]];if(!length(requirements))return(shiny::p("Keine nicht-leeren Schlüssel in dieser Kategorie."));lapply(seq_along(requirements),function(index){item<-requirements[[index]];selected<-if(length(requirements)==1L)default_ref else "";shiny::selectInput(sprintf("activity_quick_map_%s_%03d",singular,index),paste(item$source_label,"·",item$row_count,"Verwendung(en)"),choices=choice_vector(choices),selected=selected)})}
    shiny::tagList(shiny::tags$h4("Explizite Schlüsselzuordnung"),shiny::tags$h5("Portfolio-Schlüssel"),make("portfolios","portfolio",catalog$portfolios,shiny::isolate(input$activity_quick_portfolio)),shiny::tags$h5("Konto-Schlüssel einschließlich Transferziel"),make("accounts","account",catalog$accounts,shiny::isolate(input$activity_quick_default_account)),shiny::tags$h5("Asset-Schlüssel einschließlich Quell-Asset"),make("assets","asset",catalog$assets,shiny::isolate(input$activity_quick_asset)))
  })
  output$activity_quick_profile_state <- shiny::renderUI({
    model<-activity_quick_profiles();loaded<-activity_quick_loaded_profile()
    if(is.null(model))return(portelyra_status_panel("Zuordnungsprofile nicht gelesen","Profile liegen lokal beim Eigentümer und sind an die aktive Laufzeitumgebung gebunden."))
    portelyra_status_panel(if(is.null(loaded))paste(model$profile_count,"Zuordnungsprofile verfügbar")else paste("Profil geladen ·",loaded$public_profile$profile_label),paste("Standardprofil:",if(any(vapply(model$profiles,function(row)isTRUE(row$is_standard),logical(1L))))"vorhanden"else"nicht gesetzt","· Schreiben in die Stammdaten: 0"),tone="neutral")
  })
  output$activity_quick_template <- shiny::downloadHandler(filename=function()"portelyra-activity.csv",content=function(file){source<-file.path(project_root,"contracts/redundant-asset-activity-csv/v1/portelyra-activity.csv");if(!file.exists(source))stop("data_activity_quick_import_source_required",call.=FALSE);file.copy(source,file,overwrite=TRUE)},contentType="text/csv")
  output$activity_draft_editable <- shiny::renderText({model<-activity_draft_open();if(!is.null(model)&&isTRUE(model$can_edit))'yes'else'no'})
  shiny::outputOptions(output,'activity_draft_editable',suspendWhenHidden=FALSE)
  output$activity_draft_value_ui <- shiny::renderUI({
    field<-input$activity_draft_field;catalog<-activity_catalog();model<-activity_draft_open();if(is.null(model)||!isTRUE(model$can_edit)||is.null(field)||!nzchar(field)||is.null(catalog))return(NULL)
    if(field%in%c("account_ref","related_account_ref")){selected<-if(is.null(model))""else model[[field]];return(shiny::selectInput("activity_draft_value_ref","Konto aus dem Register",choice_vector(catalog$accounts),selected=selected))}
    if(field%in%c("asset_ref","source_asset_ref")){selected<-if(is.null(model))""else model[[field]];return(shiny::selectInput("activity_draft_value_ref","Asset aus dem Register",choice_vector(catalog$assets),selected=selected))}
    current<-if(is.null(model)||is.null(model$event_summary[[field]]))""else model$event_summary[[field]]
    shiny::textInput("activity_draft_value_text","Exakter Textwert",current)
  })
  output$activity_draft_valuation_ui <- shiny::renderUI({
    model<-activity_draft_open();if(is.null(model)||!identical(model$valuation_summary$lifecycle,"valuation_pending")||!identical(model$event_summary$event_type,"reward"))return(NULL)
    currency<-model$valuation_summary$price_currency
    shiny::div(class="pl-write-boundary",
      shiny::tags$h4("Fehlende Reward-Bewertung nachpflegen"),
      shiny::p(class="pl-section-copy","Fiat-Gesamtwert bezieht sich auf die Nettomenge nach Asset-Gebühr. Nicht terminierende Stückpreise werden nicht gerundet; dann bitte den exakten Stückpreis eingeben."),
      shiny::div(class="pl-form-grid",
        shiny::selectInput("activity_draft_valuation_mode","Eingabe",c("Fiat-Gesamtwert nach Fee"="manual_fiat_total","Exakter Stückpreis"="manual_unit_price")),
        shiny::textInput("activity_draft_valuation_value","Exakter Wert",""),
        shiny::textInput("activity_draft_valuation_currency","Währung",if(is.null(currency))""else currency)
      ),
      shiny::actionButton("activity_draft_valuation_apply","Manuelle Bewertung im Entwurf speichern",class="btn-default")
    )
  })
  output$activity_draft_state <- shiny::renderUI({
    model<-activity_draft_open();if(is.null(model))return(portelyra_status_panel("Kein offener Buchungsentwurf ausgewählt","Laden ist nur lesend und stellt nur flüchtige Browserkennungen wieder her."))
    if(!is.null(model$batch_preview))return(portelyra_status_panel(paste('Gemeinsames Storno ·',model$selected_event_count,'Buchungen ·',model$status),
      if(identical(model$status,'applying'))'Gespeicherte ursprüngliche Auswahl und Vorschau. Nur aktiven Beleg abgleichen oder dieselbe Auswahl frisch bestätigen. Abweichende Generationen blockieren; nicht neu anlegen.'else if(identical(model$status,'committed'))'Abgeschlossen. Historische Generationen bleiben erhalten. Keine erneute Buchung.'else'Gespeicherte gemeinsame Vorschau prüfen und ausdrücklich bestätigen.',tone=if(identical(model$status,'applying'))'warning'else'neutral'))
    portelyra_status_panel(paste("Entwurf",model$status),paste("Validierung:",model$validation_status,"· Bewertung:",model$valuation_summary$lifecycle,"· fehlend:",if(length(model$missing_fields))paste(model$missing_fields,collapse=", ")else"keine","· Fassung",model$revision,"· Wiederaufnahme:",if(model$can_resume)"explizit möglich"else"nicht erforderlich"),tone=if(model$can_resume)"error"else if(model$can_confirm)"neutral"else"warning")
  })
  output$activity_draft_fee_resolution_ui <- shiny::renderUI({
    model<-activity_draft_open();if(is.null(model)||!isTRUE(model$can_resolve_unclassified_fee))return(NULL)
    fee<-model$unclassified_fee_summary$decimal;choices<-c("Als monetäre Gebühr buchen"="monetary_fee","Als Asset-Gebührenmenge buchen"="asset_fee_quantity")
    if(is.character(fee)&&length(fee)==1L&&!is.na(fee)&&grepl("^-?0+(\\.0+)?$",fee))choices<-c(choices,"Explizit null – Quellwert ist null"="zero_no_fee")
    shiny::div(class="pl-editor-actions",shiny::strong(paste("Unklassifizierte Gebühr aus der Quelle:",fee)),shiny::selectInput("activity_draft_fee_role","Gebührenrolle",choices),shiny::actionButton("activity_draft_fee_resolve","Gebührenrolle im Entwurf binden",class="btn-default"))
  })
  output$activity_draft_detail <- shiny::renderTable({
    model<-activity_draft_open();catalog<-activity_catalog();if(is.null(model)||is.null(catalog))return(data.frame())
    label_for<-function(rows,ref){if(is.null(ref)||!nzchar(ref))return("");matches<-Filter(function(row)identical(row$ref,ref),rows);if(length(matches)==1L)matches[[1L]]$label else ""}
    values<-c(list(Source_Zeile=if(is.null(model$source_row_ordinal))""else model$source_row_ordinal,Source_Row_Key=if(is.null(model$source_row_key))""else model$source_row_key,Unklassifizierte_Gebühr=if(is.null(model$unclassified_fee_summary$decimal))""else model$unclassified_fee_summary$decimal,Gebührenrolle=model$unclassified_fee_summary$status,Bewertungsherkunft=model$valuation_summary$origin,Bewertungsstatus=model$valuation_summary$lifecycle,Bewertungswährung=if(is.null(model$valuation_summary$price_currency))""else model$valuation_summary$price_currency,Portfolio=label_for(catalog$portfolios,model$portfolio_ref),Konto=label_for(catalog$accounts,model$account_ref),Zielkonto=label_for(catalog$accounts,model$related_account_ref),Asset=label_for(catalog$assets,model$asset_ref),Source_Asset=label_for(catalog$assets,model$source_asset_ref)),model$event_summary)
    data.frame(Feld=names(values),Wert=vapply(values,function(value)if(is.null(value))""else as.character(value),character(1L)),check.names=FALSE,stringsAsFactors=FALSE)
  },striped=TRUE,bordered=TRUE)
  output$activity_draft_rows <- shiny::renderTable({
    model<-activity_draft_list();if(is.null(model))return(data.frame())
    data_activity_draft_open_frame_v1(model$drafts,activity_draft_reasons())
  },striped=TRUE,bordered=TRUE)
  activity_csv_scope_note <- shiny::reactiveVal(NULL)
  output$activity_csv_scope_note <- shiny::renderUI({note<-activity_csv_scope_note();if(is.null(note))NULL else portelyra_status_panel("Anderes Portfolio gewählt",note,tone="warning")})
  output$activity_csv_state <- shiny::renderUI({model<-activity_csv_inspection();preview<-activity_csv_preview();if(is.null(model))return(NULL)
    if(is.null(preview))return(portelyra_status_panel(paste(model$row_count,"Zeilen gelesen"),if(identical(model$status,"mapping_required"))"Zuordnung nötig, dann „Zuordnung übernehmen“."else"Noch keine Vorschau.",tone="warning"))
    shiny::tagList(portelyra_status_panel(switch(preview$status,ready_for_confirmation="Bereit zur Übernahme",nothing_to_import="Nichts zu übernehmen","Import blockiert"),
      paste(preview$ready_row_count,"neu ·",preview$unchanged_row_count,"unverändert ·",preview$blocked_row_count,"blockiert"),
      tone=switch(preview$status,ready_for_confirmation="warning",nothing_to_import="neutral","error")),
      # Umfang je Portfolio (#551): Zeilen einer nicht gewaehlten Klasse sperren mit Grund; dazunehmen oder aus der Datei entfernen.
      data_asset_activity_csv_scope_ui_v1(preview,data_settings_open_target_js_v1("portfolio-configuration-change")))})
  shiny::observeEvent(input$activity_csv_scope_add,{
    preview<-activity_csv_preview();keys<-vapply(preview$scope_classes,function(item)as.character(item$key),character(1L))
    target<-tryCatch(.data_asset_activity_resolve(.data_asset_activity_selection(activity_editor,runtime$context),"portfolios",input$activity_portfolio)$portfolio_id,error=function(error)NULL)
    shown<-portfolio_configuration$portfolio()
    if(!is.list(shown)||!identical(shown$portfolio_id,target)){
      activity_csv_scope_note(paste0("„Umfang dieses Portfolios“ zeigt das oben in „Assets pflegen“ gewählte Portfolio",if(is.list(shown))paste0(" „",shown$label,"“")else"",
        ". Diese Datei bucht in „",preview$scope_portfolio_label%||%"–","“ – bitte dort zuerst dieses Portfolio wählen."));return()}
    activity_csv_scope_note(NULL);portfolio_configuration$request_classes(setdiff(keys,"cash"))})
  output$activity_csv_mappings <- shiny::renderUI({model<-activity_csv_inspection();if(is.null(model))return(NULL);make<-function(items,prefix){lapply(seq_along(items),function(index){item<-items[[index]];choices<-stats::setNames(vapply(item$choices,`[[`,character(1L),"mapping_ref"),vapply(item$choices,function(choice)paste(choice$label,"·",choice$type),character(1L)));shiny::selectInput(sprintf("%s_%03d",prefix,index),paste(item$source_key,"·",item$mapping_status),choices=c("Bitte zuordnen"="",choices),selected=if(is.null(item$auto_mapping_ref))""else item$auto_mapping_ref)})};if(!identical(model$status,"mapping_required"))return(NULL);shiny::tagList(shiny::tags$h4("Assets zuordnen"),make(model$asset_mappings,"activity_csv_asset_mapping"),shiny::tags$h4("Konten zuordnen"),make(model$account_mappings,"activity_csv_account_mapping"))})
  output$activity_csv_mapping_needed <- shiny::renderText({model<-activity_csv_inspection();if(!is.null(model)&&identical(model$status,"mapping_required"))"yes"else"no"})
  shiny::outputOptions(output,"activity_csv_mapping_needed",suspendWhenHidden=FALSE)
  output$activity_csv_preview <- shiny::renderTable(data_asset_activity_csv_rows_frame_v1(activity_csv_preview()),striped=TRUE,bordered=TRUE)
  output$activity_csv_template <- shiny::downloadHandler(filename=function()"portelyra-asset-activity.csv",content=function(file)data_asset_activity_csv_template_v1(file,project_root),contentType="text/csv")
  # Was die gewaehlte Aktion schreibt - ein Satz statt eines Felderwaldes. Bei
  # Korrektur und Ersetzung richten sich die Ersatzfelder nach den gewaehlten
  # Vorgaengern; solange keiner gewaehlt ist, bleiben alle sichtbar (#422).
  # Pflegestand je Asset und Konto (#423, Schritt 1: nur lesen).
  asset_maintenance_value <- shiny::reactiveVal(NULL)
  asset_maintenance_center <- new_data_asset_maintenance_center_v1(
    new_data_asset_maintenance_product_adapter_v1(project_root, runtime$context))
  shiny::observeEvent(input$asset_maintenance_read, {
    asset_maintenance_value(tryCatch(
      shiny::withProgress(message="Pflegestand wird gelesen",value=0.3,{
        data_asset_maintenance_read_v1(asset_maintenance_center, runtime$context, Sys.Date())}),
      error=function(error)list(status="error",
        error_code=if(is.null(error$code))"data_asset_maintenance_adapter_failed" else as.character(error$code))))
  })
  output$asset_maintenance_state <- shiny::renderUI({
    value <- asset_maintenance_value()
    if(is.null(value)) return(shiny::p(class="pl-field-hint","Noch nicht gelesen."))
    if(identical(value$status,"error"))
      return(portelyra_status_panel("Pflegestand nicht gelesen",pl_error_text_v1(value$error_code),tone="error"))
    summary <- data_asset_maintenance_summary_v1(value)
    portelyra_status_panel(summary$title, summary$copy, tone=summary$tone)
  })
  output$asset_maintenance_table <- shiny::renderTable({
    value <- asset_maintenance_value()
    if(is.null(value)||identical(value$status,"error")) return(NULL)
    data_asset_maintenance_frame_v1(value)
  }, bordered=TRUE, striped=TRUE, spacing="s")
  # Der Pflegestand laedt wie Katalog und Bereitschaft von selbst: Er ist
  # abfragefrei, lesend und ohne Providerzugriff. Nur dann kann die
  # Transaktionsmaske sagen, dass eine Buchung vor einem erklaerten Stand liegt.
  asset_maintenance_refresh <- function() {
    asset_maintenance_value(tryCatch(
      data_asset_maintenance_read_v1(asset_maintenance_center, runtime$context, Sys.Date()),
      error=function(error) NULL))
    invisible(NULL)
  }
  asset_maintenance_autoload <- function() {
    if(!is.null(asset_maintenance_value())) return(invisible(NULL))
    asset_maintenance_refresh()
  }
  # Ohne ignoreInit: Der Transaktions-Reiter ist beim Start offen. Mit ignoreInit
  # blieb der Pflegestand bis zum ersten Reiterwechsel oder zur ersten Buchung
  # ungelesen, und der Hinweis an der Maske schwieg solange.
  shiny::observeEvent(input$asset_center_step, {
    if(identical(input$asset_center_step,"transactions")) asset_maintenance_autoload()
  })
  # Das Paar aus dem Formular im gelesenen Pflegestand. Verglichen wird ueber den
  # Anzeigenamen, nie ueber positionsabhaengige Refs - die gelten nur in ihrem
  # eigenen Katalog (rc.223).
  activity_maintenance_pair <- function() {
    value <- asset_maintenance_value()
    model <- activity_catalog()
    if(is.null(value)||is.null(model)||!is.list(value$pairs)||!length(value$pairs)) return(NULL)
    label <- function(area, ref) {
      if(!is.character(ref)||length(ref)!=1L||!nzchar(ref)) return(NULL)
      treffer <- Filter(function(row) identical(row$ref, ref), model[[area]])
      if(length(treffer)==1L) treffer[[1L]]$label else NULL
    }
    asset <- label("assets", input$activity_asset)
    konto <- label("accounts", input$activity_account)
    if(is.null(asset)||is.null(konto)) return(NULL)
    treffer <- Filter(function(row) identical(row$asset_label,asset) && identical(row$account_label,konto), value$pairs)
    if(length(treffer)==1L) treffer[[1L]] else NULL
  }
  output$activity_maintenance_hint <- shiny::renderUI({
    paar <- activity_maintenance_pair()
    if(is.null(paar)) return(NULL)
    spur <- paar$tracks$trade
    if(is.null(spur)||!identical(spur$state,"complete_through")||is.null(spur$through_date)) return(NULL)
    datum <- input$activity_date
    if(!inherits(datum,"Date")||length(datum)!=1L||is.na(datum)) return(NULL)
    if(format(datum,"%Y-%m-%d") > spur$through_date) return(NULL)
    portelyra_status_panel(
      paste("Dieses Paar ist bis", .data_asset_maintenance_datum(spur$through_date), "als vollständig erklärt"),
      paste("Die Buchung liegt davor und ändert damit eine abgeschlossene Historie.",
        "Gespeichert wird sie trotzdem; der Pflegestand dieses Paares geht danach auf den Tag vor der Buchung zurück."),
      tone="warning")
  })
  # --- Pflegestand erklaeren (#423, Schritt 2) ------------------------------
  asset_maintenance_preview <- shiny::reactiveVal(NULL)
  asset_maintenance_runs <- shiny::reactiveVal(NULL)
  asset_maintenance_notice <- shiny::reactiveVal(NULL)
  # Die Auswahlliste der Paare kommt aus dem gelesenen Stand. Gewaehlt wird ueber
  # die Paarkennung, nicht ueber den Anzeigenamen: Assetnamen sind nicht
  # eindeutig, und ein Asset liegt auf mehreren Konten.
  asset_maintenance_choices <- function(value) {
    if(is.null(value)||!is.list(value$pairs)||!length(value$pairs)) return(c("Erst Pflegestand lesen"=""))
    labels <- vapply(value$pairs, function(row) paste0(
      row$asset_label, " · ", row$account_label, " · ",
      if(identical(row$effective_state,"not_maintained")) "ohne Stand"
      else .data_asset_maintenance_datum(row$effective_through_date)), character(1L))
    stats::setNames(vapply(value$pairs, function(row) as.character(row$pair_ref), character(1L)), labels)
  }
  shiny::observeEvent(asset_maintenance_value(), {
    value <- asset_maintenance_value()
    if(is.null(value)||identical(value$status,"error")) return(invisible(NULL))
    # Kein server=TRUE: Die Paarliste liegt vollstaendig im gelesenen Stand, und
    # eine laufende serverseitige Selectize-Ladung kann die naechste
    # Aktualisierung einer anderen Auswahl ueberholen - dieselbe Begruendung wie
    # in asset_center_refresh().
    shiny::updateSelectizeInput(session,"asset_maintenance_pairs",
      choices=asset_maintenance_choices(value), selected=character(), server=FALSE)
    # Ein neuer Stand entwertet eine offene Vorschau.
    asset_maintenance_preview(NULL)
    shiny::updateCheckboxInput(session,"asset_maintenance_confirm",value=FALSE)
  }, ignoreInit=TRUE, ignoreNULL=TRUE)
  asset_maintenance_request <- function() {
    umfang <- input$asset_maintenance_scope
    if(identical(umfang,"retract"))
      data_asset_maintenance_request_v1("selected", pair_refs=input$asset_maintenance_pairs, state="not_maintained")
    else
      data_asset_maintenance_request_v1(umfang, through_date=input$asset_maintenance_through,
        pair_refs=if(identical(umfang,"selected")) input$asset_maintenance_pairs else character())
  }
  asset_maintenance_failed <- function(error) {
    asset_maintenance_notice(list(tone="error", title="Pflegeerklärung blockiert",
      copy=pl_error_text_v1(if(is.null(error$code)) conditionMessage(error) else error$code)))
    NULL
  }
  shiny::observeEvent(input$asset_maintenance_prepare, {
    asset_maintenance_notice(NULL)
    shiny::updateCheckboxInput(session,"asset_maintenance_confirm",value=FALSE)
    value <- tryCatch(data_asset_maintenance_preview_v1(asset_maintenance_center, runtime$context,
      asset_maintenance_request(), Sys.Date()), error=asset_maintenance_failed)
    asset_maintenance_preview(value)
    if(!is.null(value)) asset_maintenance_notice(NULL)
  })
  # Das Haekchen bindet genau diese Vorschau. Eine neue Vorschau hebt es auf.
  shiny::observeEvent(input$asset_maintenance_confirm, {
    preview <- asset_maintenance_preview()
    if(!isTRUE(input$asset_maintenance_confirm)||is.null(preview)) return(invisible(NULL))
    tryCatch(data_asset_maintenance_confirm_v1(asset_maintenance_center, runtime$context,
      preview$preview_fingerprint), error=asset_maintenance_failed)
  }, ignoreInit=TRUE)
  shiny::observeEvent(input$asset_maintenance_apply, {
    preview <- asset_maintenance_preview()
    if(is.null(preview)||!isTRUE(input$asset_maintenance_confirm)) {
      asset_maintenance_notice(list(tone="warning", title="Bestätigung fehlt",
        copy="Zuerst die Erklärung prüfen und die Vorschau ausdrücklich bestätigen."))
      return(invisible(NULL))
    }
    jetzt <- format(as.POSIXct(Sys.time(), tz="UTC"), "%Y-%m-%dT%H:%M:%SZ")
    result <- tryCatch(data_asset_maintenance_apply_v1(asset_maintenance_center, runtime$context,
      preview$preview_fingerprint, jetzt), error=asset_maintenance_failed)
    shiny::updateCheckboxInput(session,"asset_maintenance_confirm",value=FALSE)
    asset_maintenance_preview(NULL)
    if(is.null(result)) return(invisible(NULL))
    asset_maintenance_value(tryCatch(
      data_asset_maintenance_read_v1(asset_maintenance_center, runtime$context, Sys.Date()),
      error=function(error) asset_maintenance_value()))
    asset_maintenance_runs(tryCatch(
      data_asset_maintenance_runs_v1(asset_maintenance_center, runtime$context),
      error=function(error) NULL))
    asset_maintenance_notice(list(
      tone=if(identical(result$status,"already_applied")) "warning" else "positive",
      title=if(identical(result$status,"already_applied")) "Dieser Vorgang lag bereits vor"
        else if(identical(result$state,"not_maintained")) "Zusicherung zurückgenommen"
        else "Pflegestand erklärt",
      copy=paste(result$declared_pair_count, "Asset-Konto-Paare ·",
        if(is.null(result$through_date)) "ohne Stand" else paste("geprüft bis", .data_asset_maintenance_datum(result$through_date)),
        "· Pflegelauf", result$run_ref, "· keine Buchung, kein Kursabruf")))
  })
  shiny::observeEvent(input$asset_maintenance_runs_read, {
    asset_maintenance_runs(tryCatch(
      data_asset_maintenance_runs_v1(asset_maintenance_center, runtime$context),
      error=function(error) list(status="error",
        error_code=if(is.null(error$code))"data_asset_maintenance_adapter_failed" else as.character(error$code))))
  })
  output$asset_maintenance_preview_state <- shiny::renderUI({
    preview <- asset_maintenance_preview()
    if(is.null(preview)) return(shiny::p(class="pl-field-hint","Noch keine Vorschau. „Erklärung prüfen“ schreibt nichts."))
    summary <- data_asset_maintenance_preview_summary_v1(preview)
    portelyra_status_panel(summary$title, summary$copy, tone=summary$tone)
  })
  output$asset_maintenance_preview_table <- shiny::renderTable({
    preview <- asset_maintenance_preview()
    if(is.null(preview)||!length(preview$included)) return(NULL)
    rows <- preview$included
    if(length(rows)>60L) rows <- rows[seq_len(60L)]
    data.frame(
      Asset=vapply(rows,function(row).data_asset_maintenance_kurz(row$asset_label),character(1L)),
      Konto=vapply(rows,function(row).data_asset_maintenance_kurz(row$account_label),character(1L)),
      Bisher=vapply(rows,function(row)if(is.null(row$previous_through_date))"ohne Stand" else .data_asset_maintenance_datum(row$previous_through_date),character(1L)),
      `Letzte Buchung`=vapply(rows,function(row).data_asset_maintenance_datum(row$last_event_date),character(1L)),
      Befund=vapply(rows,function(row)if(isTRUE(row$movement_since_previous_state))"Bewegung seit dem letzten Stand" else "",character(1L)),
      check.names=FALSE,stringsAsFactors=FALSE)
  }, bordered=TRUE, striped=TRUE, spacing="s")
  output$asset_maintenance_action_feedback <- shiny::renderUI({
    notice <- asset_maintenance_notice()
    if(is.null(notice)) return(NULL)
    portelyra_status_panel(notice$title, notice$copy, tone=notice$tone)
  })
  output$asset_maintenance_runs_state <- shiny::renderUI({
    value <- asset_maintenance_runs()
    if(is.null(value)) return(shiny::p(class="pl-field-hint","Noch nicht gelesen."))
    if(identical(value$status,"error"))
      return(portelyra_status_panel("Pflegeläufe nicht gelesen",pl_error_text_v1(value$error_code),tone="error"))
    portelyra_status_panel(
      sprintf("%d Pflegelauf%s · %d erklärte Paare", as.integer(value$run_count),
        if(identical(as.integer(value$run_count),1L))"" else "läufe", as.integer(value$declared_pair_count)),
      if(is.null(value$newest_declared_at_utc)) "Noch keine Erklärung abgegeben."
      else paste("Jüngste Erklärung", sub("T"," ",sub("Z$","",value$newest_declared_at_utc)),
        "· älteste", sub("T"," ",sub("Z$","",value$oldest_declared_at_utc))),
      tone="neutral")
  })
  output$asset_maintenance_runs_table <- shiny::renderTable({
    value <- asset_maintenance_runs()
    if(is.null(value)||identical(value$status,"error")) return(NULL)
    data_asset_maintenance_runs_frame_v1(value)
  }, bordered=TRUE, striped=TRUE, spacing="s")
  # --- Pruefstempel am Asset-Stand (#423) -----------------------------------
  # Eine eigene Zentrale: Jede haelt genau eine offene Vorschau. Teilten sich
  # Stempel und Abschluss-Karte eine, entwertete die Vorschau der einen still die
  # der anderen.
  activity_stamp_center <- new_data_asset_maintenance_center_v1(
    new_data_asset_maintenance_product_adapter_v1(project_root, runtime$context))
  activity_stamp_preview <- shiny::reactiveVal(NULL)
  activity_stamp_notice <- shiny::reactiveVal(NULL)
  activity_stamp_sent <- NULL
  # Das Asset kommt aus der Suche des Asset-Centers, wie bei der Buchungstabelle;
  # der Pflegestand kennt es ueber seinen Namen.
  activity_stamp_model <- shiny::reactive({
    katalog <- asset_center_catalog()
    gewaehlt <- input$asset_center_asset
    treffer <- if (is.null(katalog) || !is.character(gewaehlt) || length(gewaehlt) != 1L || !nzchar(gewaehlt)) NULL
      else tryCatch(data_asset_center_selected_v1(katalog, gewaehlt), error = function(error) NULL)
    name <- if (is.null(treffer)) NULL else treffer$display_name
    gleiche <- if (is.null(name)) 1L else
      sum(vapply(katalog$assets, function(row) identical(row$display_name, name), logical(1L)))
    activity <- activity_catalog()
    konto <- if (is.null(activity)) list() else Filter(function(row) identical(row$ref, input$activity_account), activity$accounts)
    stand <- asset_maintenance_value()
    # Ohne eine einzige Buchung gibt es kein Ledger, und der Pflegestand laesst
    # sich nicht lesen. Das ist "leer", nicht "ungelesen".
    liste <- correction_model()
    if (is.null(stand) && !is.null(liste) && !length(liste$candidates)) stand <- list(status = "available", pairs = list())
    data_asset_maintenance_stamp_model_v1(stand, name, gleiche,
      if (length(konto) == 1L) konto[[1L]]$label else NULL)
  })
  # Die Kaestchen werden nur neu geschickt, wenn sich Angebot oder Vorbelegung
  # aendern - sonst naehme jede Buchung dem Eigentuemer seine Haken weg. Ohne
  # ignoreInit: Der erste Stand ist der beim Sitzungsstart.
  shiny::observeEvent(activity_stamp_model(), {
    model <- activity_stamp_model()
    angebot <- list(choices = model$choices, selected = model$selected)
    if (identical(angebot, activity_stamp_sent)) return(invisible(NULL))
    activity_stamp_sent <<- angebot
    shiny::updateCheckboxGroupInput(session, "activity_stamp_pairs",
      choices = if (length(model$choices)) model$choices else character(0), selected = model$selected)
    activity_stamp_preview(NULL)
  })
  # Ein anderes Asset: Die Meldung ueber den letzten Stempel gehoert nicht mehr dazu.
  shiny::observeEvent(input$asset_center_asset, activity_stamp_notice(NULL), ignoreInit = TRUE, ignoreNULL = FALSE)
  # Heute als Stichtag vorbelegt, sichtbar und aenderbar. Der Kern weist einen
  # Stichtag in der Zukunft ab.
  shiny::observeEvent(TRUE, shiny::updateDateInput(session, "activity_stamp_through", value = Sys.Date()), once = TRUE)
  shiny::observeEvent(list(input$activity_stamp_pairs, input$activity_stamp_through), activity_stamp_preview(NULL),
    ignoreInit = TRUE, ignoreNULL = FALSE)
  activity_stamp_failed <- function(error) {
    activity_stamp_notice(list(tone = "error", title = "Stempel nicht gesetzt",
      copy = pl_error_text_v1(if (is.null(error$code)) conditionMessage(error) else error$code)))
    NULL
  }
  shiny::observeEvent(input$activity_stamp_prepare, {
    activity_stamp_notice(NULL); activity_stamp_preview(NULL)
    model <- activity_stamp_model()
    refs <- intersect(as.character(input$activity_stamp_pairs), unname(model$choices))
    datum <- input$activity_stamp_through
    if (!identical(model$status, "ready") || !length(refs)) {
      activity_stamp_notice(list(tone = "warning", title = "Kein Konto gewählt",
        copy = "Mindestens ein Konto ankreuzen, das mit dem Broker abgeglichen ist.")); return(invisible(NULL))
    }
    if (!inherits(datum, "Date") || length(datum) != 1L || is.na(datum)) {
      activity_stamp_notice(list(tone = "warning", title = "Stichtag fehlt",
        copy = "Den Tag eintragen, bis zu dem geprüft ist.")); return(invisible(NULL))
    }
    # Der Kern weist das ebenfalls ab, aber nur mit einem Sammelcode.
    if (datum > Sys.Date()) {
      activity_stamp_notice(list(tone = "warning", title = "Stichtag liegt in der Zukunft",
        copy = "Was noch nicht war, kann nicht geprüft sein. Spätestens heute.")); return(invisible(NULL))
    }
    activity_stamp_preview(tryCatch(data_asset_maintenance_preview_v1(activity_stamp_center, runtime$context,
      data_asset_maintenance_request_v1("selected", through_date = datum, pair_refs = refs), Sys.Date()),
      error = activity_stamp_failed))
  })
  shiny::observeEvent(input$activity_stamp_apply, {
    preview <- activity_stamp_preview()
    if (is.null(preview) || identical(as.integer(preview$included_count), 0L)) {
      activity_stamp_notice(list(tone = "warning", title = "Vorschau fehlt",
        copy = "Zuerst „Stempel prüfen“; gesetzt wird genau, was dort steht.")); return(invisible(NULL))
    }
    # Der zweite Klick ist die Bestaetigung genau dieser Vorschau.
    jetzt <- format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ")
    result <- tryCatch({
      data_asset_maintenance_confirm_v1(activity_stamp_center, runtime$context, preview$preview_fingerprint)
      data_asset_maintenance_apply_v1(activity_stamp_center, runtime$context, preview$preview_fingerprint, jetzt)
    }, error = activity_stamp_failed)
    activity_stamp_preview(NULL)
    if (is.null(result)) return(invisible(NULL))
    asset_maintenance_refresh()
    if (!is.null(asset_maintenance_runs())) asset_maintenance_runs(tryCatch(
      data_asset_maintenance_runs_v1(asset_maintenance_center, runtime$context), error = function(error) NULL))
    n <- as.integer(result$declared_pair_count)
    activity_stamp_notice(list(
      tone = if (identical(result$status, "already_applied")) "warning" else "positive",
      title = if (identical(result$status, "already_applied")) "Dieser Stempel lag bereits vor" else "Prüfstempel gesetzt",
      copy = paste0(n, if (identical(n, 1L)) " Konto" else " Konten", " · geprüft bis ",
        .data_asset_maintenance_datum(result$through_date), " · keine Buchung, kein Kursabruf")))
  })
  output$activity_stamp_mode <- shiny::renderText(activity_stamp_model()$status)
  shiny::outputOptions(output, "activity_stamp_mode", suspendWhenHidden = FALSE)
  output$activity_stamp_mode_preview <- shiny::renderText({
    preview <- activity_stamp_preview()
    if (is.null(preview) || identical(as.integer(preview$included_count), 0L)) "none" else "ready"
  })
  shiny::outputOptions(output, "activity_stamp_mode_preview", suspendWhenHidden = FALSE)
  output$activity_stamp_state <- shiny::renderUI({
    text <- data_asset_maintenance_stamp_text_v1(activity_stamp_model())
    if (is.null(text)) NULL else portelyra_status_panel(text$title, text$copy, tone = text$tone)
  })
  output$activity_stamp_table <- shiny::renderTable(data_asset_maintenance_stamp_frame_v1(activity_stamp_model()),
    bordered = TRUE, striped = TRUE, spacing = "s")
  output$activity_stamp_preview <- shiny::renderUI({
    preview <- activity_stamp_preview()
    if (is.null(preview)) return(NULL)
    text <- data_asset_maintenance_stamp_preview_text_v1(preview, activity_stamp_model())
    portelyra_status_panel(text$title, text$copy, tone = text$tone)
  })
  output$activity_stamp_feedback <- shiny::renderUI({
    notice <- activity_stamp_notice()
    if (is.null(notice)) NULL else portelyra_status_panel(notice$title, notice$copy, tone = notice$tone)
  })
  output$cash_action_fields <- shiny::renderUI({
    action<-input$cash_action;if(is.null(action)||!nzchar(action))return(NULL)
    satz<-switch(action,
      declare_coverage=if(identical(input$cash_coverage_mode,"complete_reconciled"))
        "Erklärt den Zeitraum als vollständig abgestimmt. Dafür zählen zusätzlich Eröffnungssaldo, Zeitangabe und Abstimmungsnachweis."
        else "Erklärt, wie das Konto in diesem Zeitraum geführt wird. Eröffnungssaldo und Abstimmung zählen nur bei „Vollständig abgestimmt“.",
      record_cash_event="Trägt eine einzelne Cash-Bewegung ein. Zielkonto nur bei internem Transfer.",
      record_interest_income="Trägt den Zinsertrag ein. Er bleibt von der Cashbewegung getrennt; eine Verknüpfung ist freiwillig.",
      record_reconciliation="Hält einen beobachteten Saldo zu einem Stichtag fest. Setzt einen vollständig abgestimmten Zeitraum voraus.",
      correct="Korrigiert die gewählten Datensätze. Welche Felder gelesen werden, richtet sich nach deren Art.",
      supersede="Ersetzt die gewählten Datensätze. Welche Felder gelesen werden, richtet sich nach deren Art.",
      void="Storniert die gewählten Datensätze. Außer der Auswahl wird kein Feld gelesen.",
      NULL)
    if(is.null(satz))return(NULL)
    shiny::p(class="pl-section-copy",satz)
  })
  output$cash_state <- shiny::renderUI({
    catalog<-cash_catalog();preview<-cash_preview();view<-cash_read_view()
    if(is.null(catalog)) return(portelyra_status_panel("Cash-Auswahl nicht geladen","Aktualisieren ist nur lesend und startet keinen Rechenlauf."))
    portelyra_status_panel(if(is.null(preview)) "Bearbeitung der Cash-Abdeckung bereit" else "Vorschau der Cash-Abdeckung wartet",paste(length(catalog$accounts),"Konten ·",length(catalog$cash_assets),"Cash-Assets ·",if(is.null(view)) 0L else view$period_count,"Abdeckungszeiträume"),tone=if(is.null(preview)) "neutral" else "warning")
  })
  output$cash_periods <- shiny::renderTable({view<-cash_read_view();if(is.null(view)||!identical(view$status,"available"))return(data.frame());desktop_workflow_rows_frame_v1(view$periods)},striped=TRUE,bordered=TRUE)
  output$cash_history <- shiny::renderTable({view<-cash_read_view();if(is.null(view)||!identical(view$status,"available"))return(data.frame());desktop_workflow_rows_frame_v1(view$cash_history)},striped=TRUE,bordered=TRUE)
  output$cash_income <- shiny::renderTable({view<-cash_read_view();if(is.null(view)||!identical(view$status,"available"))return(data.frame());desktop_workflow_rows_frame_v1(view$income_history)},striped=TRUE,bordered=TRUE)
  output$cash_receipts <- shiny::renderTable({view<-cash_read_view();if(is.null(view)||!identical(view$status,"available"))return(data.frame());desktop_workflow_rows_frame_v1(view$receipt_history)},striped=TRUE,bordered=TRUE)
  output$cash_preview <- shiny::renderTable({
    preview<-cash_preview();if(is.null(preview))return(data.frame());projection<-preview$projection
    data.frame(Feld=c("Aktion","Operation","Abdeckungszeiträume","Cash-Ereignisse","Ertragsereignisse","Fassungen","Vorgänger erhalten","Portfolio-Netto interner Transfers","Ertrag erzeugt Cash","Schreiben in die Stammdaten","Schreiben von Buchungen"),Wert=c(preview$action_type,preview$operation_type,projection$period_count,projection$cash_event_count,projection$income_event_count,if(preview$action_type%in%c("correct","supersede","void"))1L else 0L,preview$reconciliation$predecessor_preserved,projection$internal_transfer_portfolio_net_change_decimal,"nein","nein","nein"),check.names=FALSE)
  },striped=TRUE,bordered=TRUE)
  output$cash_simple_state <- shiny::renderUI({
    notice<-cash_simple_notice();preview<-cash_simple_preview()
    if(!is.null(preview)){meldung<-data_cash_booking_message_v1(preview);return(portelyra_status_panel(meldung$title,meldung$copy,tone=meldung$tone))}
    if(!is.null(notice))return(portelyra_status_panel(notice$title,notice$copy,tone=notice$tone))
    shiny::p(class="pl-field-hint","Konto, Datum, Art und Betrag genügen. „Buchung prüfen“ schreibt nichts.")
  })
  output$cash_check_state <- shiny::renderUI({
    notice<-cash_check_notice();preview<-cash_check_preview()
    if(!is.null(preview)){meldung<-data_cash_check_balance_message_v1(preview);return(portelyra_status_panel(meldung$title,meldung$copy,tone=meldung$tone))}
    if(!is.null(notice))return(portelyra_status_panel(notice$title,notice$copy,tone=notice$tone))
    shiny::p(class="pl-field-hint","Der Prüf-Saldo hebt eine Teilabdeckung auf abgestimmt. „Saldo prüfen“ schreibt nichts.")
  })
  output$cash_evidence_state <- shiny::renderUI({
    value<-cash_evidence_value()
    if(is.null(value))return(shiny::p(class="pl-field-hint","Noch nicht gelesen. Oben „Cash-Auswahl und Read Model aktualisieren“."))
    if(!identical(value$status,"available"))return(portelyra_status_panel("Noch keine Cash-Abdeckung","Die erste Buchung auf einem Konto legt sie an.",tone="neutral"))
    offen<-as.integer(value$unreconciled_count);erklaert<-as.integer(value$asserted_without_balance_count)
    portelyra_status_panel(
      sprintf("%d Cash-Konten · %d nicht abgestimmt",as.integer(value$period_count),offen),
      paste0(if(is.null(value$oldest_proof_date))"Noch kein Nachweis." else paste("Ältester Nachweis",.data_cash_coverage_datum(value$oldest_proof_date)),
        if(erklaert>0L)sprintf(" · %d ohne Saldoprüfung als vollständig erklärt",erklaert) else "",
        " · „Belegt bis“ ist der Tag des letzten Nachweises; danach gilt der Saldo nur als fortgeschrieben."),
      tone=if(offen>0L||erklaert>0L)"warning" else "neutral")
  })
  output$cash_evidence_table <- shiny::renderTable({
    value<-cash_evidence_value()
    if(is.null(value)||!identical(value$status,"available"))return(NULL)
    data_cash_coverage_evidence_frame_v1(value)
  },striped=TRUE,bordered=TRUE,spacing="s")
  output$cash_recovery_preview <- shiny::renderTable({
    preview<-cash_recovery_preview();if(is.null(preview))return(data.frame())
    data.frame(Feld=c("Status","Grund der Wiederaufnahme","Operation","Originalversuch verbraucht","Automatische Wiederholung","Separate Bestätigung"),Wert=c(preview$status,preview$recovery_reason,preview$operation_type,"ja",preview$automatic_retry,preview$confirmation_required),check.names=FALSE)
  },striped=TRUE,bordered=TRUE)
  output$asset_center_state <- shiny::renderUI({
    catalog <- asset_center_catalog()
    if (is.null(catalog)) return(portelyra_status_panel("Stammdaten werden gelesen", "Assets, Konten und Zuordnungen laden von selbst."))
    selected <- tryCatch(data_asset_center_selected_v1(catalog, input$asset_center_asset), error = function(error) NULL)
    # Ohne Wahl kein Warnton (rc.332): Beim Start ist bewusst nichts gewaehlt.
    if (is.null(selected)) return(shiny::p(class = "pl-field-hint",
      paste(length(catalog$assets), if (length(catalog$assets) == 1L) "Asset" else "Assets", "· keines gewählt. In „Manuell“ zeigt die Buchungsliste dann die neuesten Buchungen aller Assets.")))
    portelyra_status_panel(selected$display_name,
      paste(selected$asset_type, "·", selected$price_currency, "· Mengenskala", selected$quantity_scale), tone = "neutral")
  })
  output$asset_center_completion_next_action<-shiny::renderUI({
    plan<-asset_center_completion_plan()
    if(is.null(plan))return(portelyra_status_panel("Historienabschluss noch nicht geplant","Die Planung liest ausschließlich gespeicherte Nachweise zu Kursen, FX und Kurszuordnung.",tone="neutral"))
    action<-plan$next_action
    detail<-if(is.null(action$asset_name))paste("Zielwährung",plan$target_currency)else paste(action$asset_name,"· Zielwährung",plan$target_currency)
    button<-if(identical(action$code,"coverage_required"))shiny::actionButton("asset_center_completion_coverage_action",action$label,class="btn-primary")else if(identical(action$code,"ready_for_snapshot"))NULL else shiny::actionButton("asset_center_completion_asset_action",action$label,class="btn-primary")
    shiny::tagList(portelyra_status_panel(paste("Nächste Aktion ·",action$label),paste(detail,"· Plan",plan$required_start_date,"bis",plan$as_of_date,"· kein Kursabruf · kein Schreiben"),tone=if(identical(action$code,"ready_for_snapshot"))"positive"else"warning"),button)
  })
  output$asset_center_completion_plan_table<-shiny::renderTable({plan<-asset_center_completion_plan();if(is.null(plan))return(data.frame());data_asset_center_market_fx_completion_plan_frame_v1(plan)},striped=TRUE,bordered=FALSE)
  output$asset_center_completion_batch_action<-shiny::renderUI({
    plan<-asset_center_completion_plan();preview<-asset_center_completion_batch();if(is.null(plan))return(NULL)
    fetchable<-any(vapply(plan$rows,function(row)row$disposition%in%c("market_history_required","fx_history_required"),logical(1L)))
    if(!fetchable)return(NULL)
    if(is.null(preview))return(shiny::actionButton("asset_center_completion_batch_prepare","Gemeinsamen Sammelabruf für Kurse und FX prüfen",class="btn-default"))
    portelyra_status_panel("Sammelabruf unveränderlich vorbereitet",paste(preview$market_range_count,"Kursbereiche ·",preview$fx_range_count,"FX-Bereiche ·",preview$provider_call_count,"Aufrufe beim Kursanbieter · Vorschau: bisher kein Kursabruf. Ausführungsstand und getrennte Bestätigungen im gemeinsamen Bereich für den Sammelabruf darunter."),tone="warning")
  })
  output$asset_center_completion_batch<-shiny::renderTable({preview<-asset_center_completion_batch();if(is.null(preview))return(data.frame());data_asset_center_market_fx_fetch_batch_frame_v1(preview)},striped=TRUE,bordered=FALSE)
  output$asset_center_market_inventory_state <- shiny::renderUI({
    catalog <- asset_center_catalog(); providers <- asset_center_provider_catalog()
    if (is.null(catalog) || is.null(providers)) return(NULL)
    inventory <- tryCatch(data_asset_center_market_inventory_v1(catalog, providers), error = function(error) NULL)
    if (is.null(inventory)) return(portelyra_status_panel("Abdeckung blockiert", "Stammdaten oder Kurszuordnungen sind ungültig.", tone = "warning"))
    ready <- if (is.null(inventory$counts$history_ready_to_plan)) 0L else inventory$counts$history_ready_to_plan
    missing <- if (is.null(inventory$counts$mapping_missing)) 0L else inventory$counts$mapping_missing
    open <- inventory$asset_count - ready
    # Fruehere Kursreihen der Bewertungs-Zeitleiste (rc.393): bewertet der Sammellauf mit; nicht bewertbare stehen mit Namen da.
    timeline_note <- tryCatch(data_market_timeline_inventory_note_v1(asset_center_chain$valuation_inventory(TRUE)$rows),
      error = function(error) " · Bewertungs-Zeitleiste nicht lesbar")
    portelyra_status_panel(
      paste(inventory$asset_count, "providerfähige Assets"),
      paste0(paste(ready, "Historie planbar ·", missing, "ohne Kurszuordnung ·", open, "mit offenem Schritt · nur lesend"), timeline_note),
      tone = if (open > 0L) "warning" else "positive"
    )
  })
  output$asset_center_market_inventory <- shiny::renderTable({
    catalog <- asset_center_catalog(); providers <- asset_center_provider_catalog()
    if (is.null(catalog) || is.null(providers)) return(data.frame())
    data_asset_center_market_inventory_coverage_frame_v1(
      data_asset_center_market_inventory_v1(catalog, providers),
      asset_center_market_coverage(), asset_center_fx_coverage()
    )
  }, striped = TRUE, bordered = FALSE)
  output$asset_center_fx_demand_state <- shiny::renderUI({
    catalog <- asset_center_catalog(); providers <- asset_center_provider_catalog()
    if (is.null(catalog) || is.null(providers)) return(shiny::span("FX-Bedarf noch nicht geprüft"))
    demand <- tryCatch(data_asset_center_fx_demand_v1(data_asset_center_market_inventory_v1(catalog, providers), "EUR"), error = function(error) NULL)
    if (is.null(demand)) return(shiny::span("FX-Bedarf blockiert"))
    coverage <- asset_center_fx_coverage(); complete <- if (is.null(coverage)) 0L else sum(vapply(coverage$rows,function(row)identical(row$coverage_status,"complete"),logical(1L)))
    shiny::span(paste("FX-Bedarf:", demand$pair_count, if (demand$pair_count == 1L) "Währungspaar" else "Währungspaare", "·", complete, "vollständig"))
  })
  output$asset_center_fx_demand_table <- shiny::renderTable({
    catalog <- asset_center_catalog(); providers <- asset_center_provider_catalog()
    if (is.null(catalog) || is.null(providers)) return(data.frame())
    coverage <- asset_center_fx_coverage()
    if (is.null(coverage)) return(data_asset_center_fx_demand_frame_v1(data_asset_center_fx_demand_v1(data_asset_center_market_inventory_v1(catalog, providers), "EUR")))
    if (!length(coverage$rows)) return(data.frame())
    data.frame(Von=vapply(coverage$rows,`[[`,character(1L),"source_currency"),Nach=vapply(coverage$rows,`[[`,character(1L),"target_currency"),`Verwendet von`=vapply(coverage$rows,`[[`,integer(1L),"consumer_count"),Route=vapply(coverage$rows,`[[`,character(1L),"route_kind"),Beobachtet=vapply(coverage$rows,`[[`,integer(1L),"observed_day_count"),Quelllücken=vapply(coverage$rows,`[[`,integer(1L),"source_gap_day_count"),Fehlend=vapply(coverage$rows,`[[`,integer(1L),"missing_day_count"),Status=vapply(coverage$rows,`[[`,character(1L),"coverage_status"),check.names=FALSE)
  }, striped = TRUE, bordered = FALSE)
  output$asset_center_fx_search_controls <- shiny::renderUI({
    catalog<-asset_center_catalog();providers<-asset_center_provider_catalog();if(is.null(catalog)||is.null(providers))return(NULL)
    demand<-data_asset_center_fx_demand_v1(data_asset_center_market_inventory_v1(catalog,providers),"EUR");if(!length(demand$rows))return(shiny::p(class="pl-section-copy","Kein FX-Paar erforderlich."))
    choices<-stats::setNames(vapply(demand$rows,function(row)paste(row$source_currency,row$target_currency,sep="|"),character(1L)),vapply(demand$rows,function(row)paste(row$source_currency,"→",row$target_currency),character(1L)))
    selected<-unname(choices[[1L]]);parts<-strsplit(selected,"[|]",perl=TRUE)[[1L]]
    history_controls<-NULL;fxcov<-asset_center_fx_coverage();history_ready<-!is.null(asset_center_fx_promotion_result())||(!is.null(fxcov)&&any(vapply(fxcov$rows,function(row)!identical(row$route_kind,"unbound"),logical(1L))))
    if(history_ready){
      plan<-asset_center_fx_history_plan();range_control<-NULL;if(!is.null(plan)&&length(plan$ranges)){rc<-stats::setNames(vapply(plan$ranges,`[[`,character(1L),"range_ref"),vapply(plan$ranges,function(row)paste(row$start_date,"bis",row$end_date,"·",row$calendar_day_count,"Tage"),character(1L)));range_control<-shiny::selectInput("asset_center_fx_history_range","Genau einen fehlenden FX-Bereich",rc)}
      review_controls<-NULL;if(!is.null(asset_center_fx_history_review()))review_controls<-shiny::tagList(shiny::checkboxInput("asset_center_fx_history_publish_confirm","Genau diesen FX-Kandidaten veröffentlichen",FALSE),shiny::actionButton("asset_center_fx_history_publish","Bestätigt veröffentlichen (nur fortgeschrieben) · ohne erneuten Abruf",class="btn-primary"))
      history_controls<-shiny::tagList(shiny::tags$h4("Fehlende FX-Historie"),shiny::p(class="pl-section-copy","Verwendet ausschließlich die FX-Datumsfelder direkt darüber. Nach einem Fehler zuerst gespeicherte FX-Versuche lesen."),shiny::actionButton("asset_center_fx_history_plan_action","Fehlende FX-Tage nur lesend planen",class="btn-default"),range_control,shiny::actionButton("asset_center_fx_history_preview_action","Ausgewählten FX-Abruf prüfen",class="btn-default"),shiny::checkboxInput("asset_center_fx_history_fetch_confirm","Genau einen Yahoo-Abruf bestätigen",FALSE),shiny::actionButton("asset_center_fx_history_stage_action","Bestätigt abrufen und lokal beim Eigentümer vormerken",class="btn-default"),review_controls)
    }
    search_result<-asset_center_fx_search_result();probe_controls<-NULL
    if(!is.null(search_result)&&length(search_result$candidates)){
      candidate_choices<-stats::setNames(vapply(search_result$candidates,`[[`,character(1L),"ref"),vapply(search_result$candidates,function(row)paste(row$display_name,"·",row$symbol,"·",if(is.null(row$quote_currency))"—"else row$quote_currency),character(1L)))
      promotion_controls<-NULL;if(!is.null(asset_center_fx_probe_result()))promotion_controls<-shiny::tagList(shiny::actionButton("asset_center_fx_promotion_prepare","Freigabe von Devisenpaar und Testhistorie prüfen",class="btn-default"),shiny::checkboxInput("asset_center_fx_promotion_confirm","Genau dieses FX-Paar und diese Testhistorie bestätigen",FALSE),shiny::actionButton("asset_center_fx_promotion_execute","Bestätigt veröffentlichen (nur fortgeschrieben) · ohne neuen Abruf",class="btn-primary"))
      probe_controls<-shiny::tagList(shiny::tags$h4("FX-Kandidat testen"),shiny::div(class="pl-form-grid",shiny::selectInput("asset_center_fx_candidate","Genau einen Vorschlag",candidate_choices),shiny::selectInput("asset_center_fx_direction","Umrechnungsrichtung",c("Direkt: 1 Quellwährung = Rate Zielwährung"="direct","Invers: 1 Zielwährung = Rate Quellwährung"="inverse")),shiny::dateInput("asset_center_fx_probe_start","Test ab",Sys.Date()-31L,format = "dd.mm.yyyy", language = "de", weekstart = 1),shiny::dateInput("asset_center_fx_probe_end","Test bis",Sys.Date()-1L,format = "dd.mm.yyyy", language = "de", weekstart = 1)),shiny::actionButton("asset_center_fx_probe_prepare","FX-Testabruf-Vorschau",class="btn-default"),shiny::checkboxInput("asset_center_fx_probe_confirm","Genau einen FX-Testabruf bestätigen",FALSE),shiny::actionButton("asset_center_fx_probe_execute","Bestätigt testen und lokal beim Eigentümer vormerken",class="btn-default"),promotion_controls)
    }
    shiny::tagList(shiny::tags$h4("FX-Paar suchen"),shiny::div(class="pl-form-grid",shiny::selectInput("asset_center_fx_demand","Benötigtes Paar",choices=choices,selected=selected),shiny::textInput("asset_center_fx_query","Yahoo-Symbol oder Suchtext",paste(parts[[1L]],parts[[2L]]))),shiny::actionButton("asset_center_fx_search_prepare","FX-Suchvorschau erstellen",class="btn-default"),shiny::checkboxInput("asset_center_fx_search_confirm","Genau einen Yahoo-Suchabruf bestätigen",FALSE),shiny::actionButton("asset_center_fx_search_execute","Bestätigt einmal suchen",class="btn-default"),shiny::p(class="pl-section-copy","Suche, Pair-Bindung, Historienabruf und Veröffentlichung bleiben getrennte Schritte."),probe_controls,history_controls)
  })
  output$asset_center_fx_search_preview <- shiny::renderTable({p<-asset_center_fx_search_preview();if(is.null(p))return(data.frame());data.frame(Paar=input$asset_center_fx_demand,Suchtext=p$query,Provider=p$provider_id,Versuche=1L,Providerzugriff="erst nach Bestätigung",`Paar wird angelegt`="nein",`Historie wird geschrieben`="nein",check.names=FALSE)},striped=TRUE,bordered=FALSE)
  output$asset_center_fx_search_results <- shiny::renderTable({r<-asset_center_fx_search_result();if(is.null(r)||!length(r$candidates))return(data.frame());data.frame(Symbol=vapply(r$candidates,`[[`,character(1L),"symbol"),Bezeichnung=vapply(r$candidates,`[[`,character(1L),"display_name"),Börse=vapply(r$candidates,`[[`,character(1L),"exchange"),Typ=vapply(r$candidates,`[[`,character(1L),"quote_type"),Providerwährung=vapply(r$candidates,function(row)if(is.null(row$quote_currency))"—"else row$quote_currency,character(1L)),`Paar wird angelegt`="nein",`Historie wird geschrieben`="nein",check.names=FALSE)},striped=TRUE,bordered=FALSE)
  output$asset_center_fx_probe_preview <- shiny::renderTable({p<-asset_center_fx_probe_preview();if(is.null(p))return(data.frame());data.frame(Symbol=p$symbol,Von=p$source_currency,Nach=p$target_currency,Richtung=p$direction,Providerwährung=p$expected_provider_currency,`Zeitraum von`=p$start_date,`Zeitraum bis`=p$end_date,Providerzugriff="erst nach Bestätigung",`Zwischenstand lokal`="ja",`Wechselkurshistorie wird geschrieben`="nein",check.names=FALSE)},striped=TRUE,bordered=FALSE)
  output$asset_center_fx_probe_result <- shiny::renderTable({r<-asset_center_fx_probe_result();if(is.null(r))return(data.frame());data.frame(Symbol=r$symbol,Von=r$source_currency,Nach=r$target_currency,Richtung=r$direction,Providerwährung=r$provider_currency,Beobachtet=r$observed_day_count,Quelllücken=r$source_gap_day_count,Zeitzone=r$timezone_name,`Zwischenstand lokal`="ja",`Wechselkurshistorie wird geschrieben`="nein",check.names=FALSE)},striped=TRUE,bordered=FALSE)
  output$asset_center_fx_promotion_preview <- shiny::renderTable({p<-asset_center_fx_promotion_preview();if(is.null(p))return(data.frame());data.frame(Symbol=p$symbol,Von=p$source_currency,Nach=p$target_currency,Richtung=p$direction,Beobachtet=p$observed_day_count,Nichthandelstage=p$non_trading_day_count,Quelllücken=p$source_gap_day_count,Providerzugriff="nein",`Wechselkurshistorie wird geschrieben`="erst nach Bestätigung",`Erneuter Abruf`="nein",check.names=FALSE)},striped=TRUE,bordered=FALSE)
  output$asset_center_fx_promotion_result <- shiny::renderTable({r<-asset_center_fx_promotion_result();if(is.null(r))return(data.frame());data.frame(Status=r$status,Von=r$source_currency,Nach=r$target_currency,Richtung=r$direction,Neu=r$appended_day_count,Korrigiert=r$corrected_day_count,Unverändert=r$unchanged_day_count,`Erneuter Abruf`="nein",check.names=FALSE)},striped=TRUE,bordered=FALSE)
  output$asset_center_fx_attempts_table <- shiny::renderTable({
    rows<-asset_center_fx_attempts()$rows;if(!length(rows))return(data.frame())
    desktop_workflow_rows_frame_v1(lapply(rows,function(r)list(Versuch=r$attempt_ref,Status=r$state,Phase=r$category,HTTP=if(is.null(r$http_status))'—'else as.character(r$http_status),Von=if(is.null(r$start_date))'unbekannt'else r$start_date,Bis=if(is.null(r$end_date))'unbekannt'else r$end_date,Antwort_gespeichert=r$response_saved,Ohne_Ergebnis_geprüft=r$reviewed_no_result)))
  })
  output$asset_center_fx_attempts_controls <- shiny::renderUI({
    rows<-asset_center_fx_attempts()$rows;if(!length(rows))return(shiny::p('Noch keine Versuchsnachweise gelesen.'))
    rows<-Filter(function(r)!isTRUE(r$reviewed_no_result)&&!identical(r$state,'published'),rows);if(!length(rows))return(shiny::p('Alle angezeigten Versuche ohne Ergebnis wurden geprüft. Neuer Abruf nur mit neuer Vorschau und Bestätigung.'))
    choices<-stats::setNames(vapply(rows,`[[`,character(1L),'attempt_ref'),vapply(rows,function(r)paste(r$attempt_ref,r$state,r$category),character(1L)))
    shiny::tagList(shiny::selectInput('asset_center_fx_attempt_ref','Genau einen gespeicherten Versuch prüfen',choices),
      shiny::actionButton('asset_center_fx_attempt_recover','Gespeicherten Kandidaten laden · ohne Abruf'),
      shiny::p('Nur für Versuche ohne gespeichertes Ergebnis: Eine Prüfung behauptet nicht, dass kein Netzwerkabruf stattfand. Alte Nachweise bleiben erhalten; es wird weder ein Claim zurückgesetzt noch ein Abruf gestartet. Unklare Altversuche haben keinen belegten Datumsbereich.'),
      shiny::checkboxInput('asset_center_fx_attempt_ack','Genau diesen Versuch ohne gespeichertes Ergebnis als geprüft dokumentieren',FALSE),
      shiny::actionButton('asset_center_fx_attempt_review','Prüfentscheidung speichern · ohne neuen Abruf'))
  })
  shiny::observeEvent(input$asset_center_fx_attempt_ref,{shiny::updateCheckboxInput(session,'asset_center_fx_attempt_ack',value=FALSE)},ignoreInit=TRUE)
  output$asset_center_fx_history_plan <- shiny::renderTable({p<-asset_center_fx_history_plan();if(is.null(p)||!length(p$ranges))return(data.frame());data.frame(Bereich=vapply(p$ranges,`[[`,character(1L),"range_ref"),Von=vapply(p$ranges,`[[`,character(1L),"start_date"),Bis=vapply(p$ranges,`[[`,character(1L),"end_date"),Kalendertage=vapply(p$ranges,`[[`,integer(1L),"calendar_day_count"),Providerzugriff="nein",Write="nein",check.names=FALSE)},striped=TRUE,bordered=FALSE)
  output$asset_center_fx_history_fetch_preview <- shiny::renderTable({p<-asset_center_fx_history_preview();if(is.null(p))return(data.frame());data.frame(Von=p$start_date,Bis=p$end_date,Kalendertage=p$calendar_day_count,`Abrufe beim Anbieter`=p$provider_call_count,Providerzugriff="erst nach Bestätigung",`Zwischenstand lokal`="ja",`Wechselkurshistorie wird geschrieben`="nein",check.names=FALSE)},striped=TRUE,bordered=FALSE)
  output$asset_center_fx_history_review <- shiny::renderTable({r<-asset_center_fx_history_review();if(is.null(r))return(data.frame());data.frame(Von=r$start_date,Bis=r$end_date,Beobachtet=r$observed_day_count,Nichthandelstage=r$non_trading_day_count,Quelllücken=r$source_gap_day_count,`Zwischenstand lokal`="ja",`Wechselkurshistorie wird geschrieben`="nein",check.names=FALSE)},striped=TRUE,bordered=FALSE)
  output$asset_center_fx_history_publication <- shiny::renderTable({r<-asset_center_fx_history_publication();if(is.null(r))return(data.frame());data.frame(Status=r$status,Neu=r$appended_day_count,Korrigiert=r$corrected_day_count,Unverändert=r$unchanged_day_count,`Erneuter Abruf`="nein",check.names=FALSE)},striped=TRUE,bordered=FALSE)
  output$asset_center_calendar_gap_controls <- shiny::renderUI({
    v<-asset_center_calendar_gaps()
    if(is.null(v))return(shiny::p('Noch nicht gelesen: Zeitraum wählen und „Gespeicherte Abdeckung nur lesend prüfen“ anklicken.'))
    if(identical(v$status,'blocked'))return(portelyra_status_panel('Kalenderlücken-Prüfung separat blockiert',paste(pl_error_text_v1(v$error_code),'Es wird nichts automatisch repariert.'),tone='warning'))
    notice<-if(!is.null(v$unverified_binding_count)&&v$unverified_binding_count>0L)shiny::p('Ältere Kalenderbindungen ohne Kontextnachweis bleiben unbenutzt. Nur eine separate Bestätigung bindet den ausgewählten Bereich; andere Bereiche werden nicht übernommen.')else NULL
    target<-tryCatch(asset_center_calendar_target(),error=function(e)NULL)
    if(is.null(target))return(shiny::tagList(notice,shiny::p(if(!length(v$rows))'Keine offenen Kalender-/Quelllücken im gelesenen Zeitraum.'else 'Bitte einen Kurs- oder FX-Bereich auswählen.')))
    rows<-Filter(function(r)r$scope_kind==target$kind && r$consumer_ref==target$consumer && r$source_status=='source_gap',v$rows)
    dates<-data_calendar_binding_choices_v1(v$rows,target)
    corrections<-vapply(Filter(function(r)r$disposition=='calendar_correction_proposed',rows),`[[`,character(1L),'date')
    shiny::tagList(notice,shiny::p('1 · Schließtage prüfen und Kalender binden. 2 · Quellenstatus separat korrigieren. Keine Kurse werden ergänzt; offene Handelstage bleiben Quelllücken.'),
      if(length(dates))shiny::tagList(
        shiny::p(if(target$kind=='listing')'Offline-Regelvorschläge: Börse, historische Gültigkeit und Schließtage ausdrücklich prüfen.'else 'Schließtage für Devisen brauchen einen eigenen Nachweis; kein Aktienkalender wird übernommen.'),
        if(target$kind=='listing')shiny::actionButton('asset_center_calendar_select_proposals','Regelvorschläge zur Prüfung auswählen'),
        shiny::checkboxGroupInput('asset_center_calendar_closures','Zu bestätigende Schließtage',choices=dates),
        shiny::p('Eine Erweiterung erhält vorhandene bestätigte Schließtage, Sonderöffnungen und deren Gültigkeit. Die Vorschau trennt beibehaltene und neue Tage; unbestätigte Altprofile werden nicht automatisch übernommen.'),
        shiny::actionButton('asset_center_calendar_binding_prepare','Kalenderprofil-Bindung prüfen'),
        shiny::checkboxInput('asset_center_calendar_binding_confirm','Genau dieses Profil und diesen ausgewählten Bereich bestätigen',FALSE),
        shiny::actionButton('asset_center_calendar_binding_apply','Bestätigt binden',class='btn-default')),
      if(target$kind=='listing'&&length(corrections))shiny::tagList(
        shiny::p(paste(length(corrections),'kalenderbestätigte Schließtage; offene Handelstage werden nicht ausgewählt.')),
        shiny::actionButton('asset_center_calendar_batch_prepare','Alle kalenderbestätigten Tage gemeinsam prüfen'),
        shiny::checkboxInput('asset_center_calendar_batch_confirm','Genau alle Tage der angezeigten Sammelvorschau bestätigen',FALSE),
        shiny::actionButton('asset_center_calendar_batch_apply','Bestätigt gemeinsam korrigieren',class='btn-primary')),
      if(length(corrections))shiny::tagList(
        shiny::selectInput('asset_center_calendar_correction_date','Kalenderbestätigten Tag korrigieren',corrections),
        shiny::actionButton('asset_center_calendar_correction_prepare','Korrektur prüfen'),
        shiny::checkboxInput('asset_center_calendar_correction_confirm','Genau diese Korrektur bestätigen (nur fortgeschrieben)',FALSE),
        shiny::actionButton('asset_center_calendar_correction_apply','Bestätigt korrigieren',class='btn-primary')),
      if(!length(dates)&&!length(corrections))shiny::p('Keine belegbaren Korrekturvorschläge. Offene Tage bleiben ungeklärt.'))
  })
  output$asset_center_calendar_local_feedback<-shiny::renderUI({
    value<-asset_center_calendar_feedback();if(is.null(value))return(NULL)
    portelyra_status_panel(paste('Letzte Kalenderaktion ·',value$title),value$copy,tone=value$tone)
  })
  output$asset_center_calendar_batch_preview<-shiny::renderTable({
    p<-asset_center_calendar_batch_preview();if(is.null(p))return(data.frame())
    data.frame(Datum=vapply(p$rows,`[[`,character(1L),'date'),Von='source_gap',Nach='non_trading_day',
      Grund=vapply(p$rows,`[[`,character(1L),'calendar_reason'),Providerzugriff='nein',`Historie wird geschrieben`='erst nach gemeinsamer Bestätigung',check.names=FALSE)
  },striped=TRUE,bordered=FALSE)
  output$asset_center_calendar_binding_preview<-shiny::renderTable(data_calendar_binding_summary_v1(asset_center_calendar_binding_preview()))
  output$asset_center_calendar_binding_days<-shiny::renderTable(data_calendar_binding_days_v1(asset_center_calendar_binding_preview()))
  output$asset_center_calendar_correction_preview<-shiny::renderTable({p<-asset_center_calendar_correction_preview();if(is.null(p))return(data.frame());data.frame(Datum=p$date,Von=p$source_status,Nach=p$proposed_status,Grund=p$calendar_reason,Providerzugriff='nein',`Historie wird geschrieben`='erst nach Bestätigung',check.names=FALSE)})
  output$asset_center_calendar_gaps <- shiny::renderTable({
    value<-asset_center_calendar_gaps();if(is.null(value)||!length(value$rows))return(data.frame());catalog<-asset_center_catalog();labels<-if(is.null(catalog))character() else stats::setNames(vapply(catalog$assets,`[[`,character(1L),"display_name"),vapply(catalog$assets,`[[`,character(1L),"ref"));label<-function(row)if(identical(row$scope_kind,"listing")&&!is.null(labels[[row$consumer_ref]]))unname(labels[[row$consumer_ref]])else row$consumer_ref
    data.frame(Bereich=vapply(value$rows,function(row)if(identical(row$scope_kind,"listing"))"Nativer Kurs"else"FX",character(1L)),`Verwendet von`=vapply(value$rows,label,character(1L)),Datum=vapply(value$rows,`[[`,character(1L),"date"),Quellstatus=vapply(value$rows,`[[`,character(1L),"source_status"),Vorschlag=vapply(value$rows,`[[`,character(1L),"proposed_status"),Grund=vapply(value$rows,`[[`,character(1L),"reason"),Disposition=vapply(value$rows,`[[`,character(1L),"disposition"),Kalenderprofil=vapply(value$rows,function(row)if(isTRUE(row$calendar_profile_bound))"gebunden"else"fehlt",character(1L)),check.names=FALSE)
  },striped=TRUE,bordered=FALSE)
  output$asset_center_market_persisted_coverage <- shiny::renderTable({
    value <- asset_center_market_coverage(); if (is.null(value) || !length(value$rows)) return(data.frame())
    labels <- stats::setNames(vapply(asset_center_catalog()$assets, `[[`, character(1L), "display_name"), vapply(asset_center_catalog()$assets, `[[`, character(1L), "ref"))
    data.frame(Asset=vapply(value$rows,function(row)unname(labels[[row$asset_ref]]),character(1L)),Von=vapply(value$rows,function(row)if(is.null(row$first_covered_date))"—"else row$first_covered_date,character(1L)),Bis=vapply(value$rows,function(row)if(is.null(row$last_covered_date))"—"else row$last_covered_date,character(1L)),Beobachtet=vapply(value$rows,`[[`,integer(1L),"observed_day_count"),Nichthandelstage=vapply(value$rows,`[[`,integer(1L),"non_trading_day_count"),Quelllücken=vapply(value$rows,`[[`,integer(1L),"source_gap_day_count"),Fehlend=vapply(value$rows,`[[`,integer(1L),"missing_day_count"),`Fehlende Bereiche`=vapply(value$rows,`[[`,integer(1L),"missing_range_count"),Status=vapply(value$rows,`[[`,character(1L),"coverage_status"),check.names=FALSE)
  }, striped = TRUE, bordered = FALSE)
  output$asset_center_progress <- shiny::renderTable({
    catalog <- asset_center_catalog(); if (is.null(catalog)) return(data.frame())
    data_asset_center_progress_v1(
      catalog, asset_center_provider_catalog(), input$asset_center_asset,
      asset_center_tax_state(), asset_center_history_state(), asset_center_activity_state()
    )[, c("Bereich", "Status"), drop = FALSE]
  }, striped = TRUE, bordered = FALSE)
  output$asset_center_core_detail <- shiny::renderUI({
    catalog <- asset_center_catalog(); if (is.null(catalog)) return(NULL)
    selected <- tryCatch(data_asset_center_selected_v1(catalog, input$asset_center_asset), error = function(error) NULL)
    if (is.null(selected)) return(portelyra_status_panel("Kein Asset ausgewählt", "Bitte oben ein Asset wählen.", tone = "warning"))
    shiny::tagList(
      shiny::tags$h4(selected$display_name),
      shiny::p(shiny::strong(if (identical(selected$asset_type, "cash")) "Cash · nur Zinsen als Ertrag, kein FIFO, Wert 1:1" else "Wertpapier/Krypto/Fonds · FIFO und Marktbewertung")),
      shiny::p(paste("Typ:", selected$asset_type, "· Preiswährung:", selected$price_currency, "· Mengenskala:", selected$quantity_scale)),
      shiny::p(paste("Bewertung:", selected$valuation_method, "· ISIN:", if (is.null(selected$isin)) "nicht gesetzt" else selected$isin)),
      shiny::p(class = "pl-section-copy", "Das Asset ist bereits berechenbar. Kursanbieter und Steuer bleiben optionale Ergänzungen.")
    )
  })
  output$asset_center_core_preview <- shiny::renderTable({
    preview <- asset_center_core_preview(); if (is.null(preview)) return(data.frame())
    data.frame(Bereich = "Asset", Aktion = "Neu anlegen", Bezeichnung = preview$display_name, Status = preview$status, check.names = FALSE)
  }, striped = TRUE, bordered = TRUE)
  output$asset_center_price_currency_preview <- shiny::renderTable({
    preview <- asset_center_price_currency_preview(); if (is.null(preview)) return(data.frame())
    data.frame(
      Asset = preview$display_name,
      Bisher = preview$current_price_currency,
      Künftig = preview$proposed_price_currency,
      `Wechselkurs-Umrechnung` = "nein",
      `Zuordnung beim Anbieter` = "unverändert",
      Activities = "unverändert",
      check.names = FALSE
    )
  }, striped = TRUE, bordered = TRUE)
  output$asset_center_provider_online_state <- shiny::renderUI({
    data_action_feedback_panel_v1(action_feedback$read('mapping'))
  })
  output$asset_center_provider_search_preview <- shiny::renderTable({
    preview <- asset_center_provider_search_preview(); if (is.null(preview)) return(data.frame())
    data.frame(
      Provider = preview$provider_id, Suchtext = preview$query, Modus = preview$search_mode,
      `Höchstens Treffer` = preview$result_limit, Versuche = 1L,
      Providerzugriff = "noch nein", `Automatisch wiederholen` = "nein", check.names = FALSE
    )
  }, striped = TRUE, bordered = TRUE)
  output$asset_center_provider_candidates <- shiny::renderTable({
    result <- asset_center_provider_search_result(); if (is.null(result) || !length(result$candidates)) return(data.frame())
    desktop_workflow_rows_frame_v1(lapply(result$candidates, function(row) list(
      Name = row$display_name, Symbol = row$symbol, Börse = row$exchange,
      Typ = row$quote_type, Währung = if (is.null(row$quote_currency)) "—" else row$quote_currency
    )))
  }, striped = TRUE, bordered = FALSE)
  output$asset_center_provider_probe_preview <- shiny::renderTable({
    preview <- asset_center_provider_probe_preview(); if (is.null(preview)) return(data.frame())
    data.frame(
      Provider = preview$provider_id, Symbol = preview$provider_symbol,
      `Erwartete Währung` = preview$expected_currency, Von = preview$start_date, Bis = preview$end_date,
      Versuche = 1L, Providerzugriff = "noch nein", `Historie wird geschrieben` = "nein", check.names = FALSE
    )
  }, striped = TRUE, bordered = TRUE)
  output$asset_center_provider_probe_result <- shiny::renderUI({
    result <- asset_center_provider_probe_result(); if (is.null(result)) return(NULL)
    portelyra_status_panel(
      if (isTRUE(result$currency_match)) "Testabruf plausibel" else "Währungsabweichung im Testabruf",
      paste(
        result$observed_day_count, "beobachtete Tage ·", result$exchange, "·", result$timezone_name,
        "· Prüfung der Splits:", if (isTRUE(result$split_review_required)) "erforderlich" else "nein",
        "· noch keine Bewertungsautorität"
      ),
      tone = if (isTRUE(result$currency_match) && !isTRUE(result$split_review_required)) "positive" else "warning"
    )
  })
  output$asset_center_promotion_preview <- shiny::renderTable({
    preview <- asset_center_provider_promotion_preview(); if (is.null(preview)) return(data.frame())
    data.frame(
      Markt = preview$market_code, Zeitzone = preview$timezone_name,
      Kalender = preview$calendar_code, Von = preview$start_date, Bis = preview$end_date,
      Beobachtet = preview$observed_day_count, Nichthandelstage = preview$non_trading_day_count,
      Quelllücken = preview$source_gap_day_count, Providerzugriff = "nein",
      `Historie wird geschrieben` = "nach Bestätigung", check.names = FALSE
    )
  }, striped = TRUE, bordered = TRUE)
  output$asset_center_promotion_result <- shiny::renderUI({
    result <- asset_center_provider_promotion_result(); if (is.null(result)) return(NULL)
    portelyra_status_panel(
      "Testhistorie persistent",
      paste(result$observed_day_count, "beobachtet ·", result$non_trading_day_count, "Nichthandelstage ·", result$source_gap_day_count, "Quelllücken · Kurszuordnung noch nicht verifiziert"),
      tone = if (result$source_gap_day_count > 0L || isTRUE(result$corporate_action_review_required)) "warning" else "positive"
    )
  })
  output$asset_center_mapping_verify_preview <- shiny::renderTable({
    preview <- asset_center_mapping_verify_preview(); if (is.null(preview)) return(data.frame())
    data.frame(
      Asset = preview$asset_label, Provider = preview$provider_id, Symbol = preview$provider_symbol,
      Währung = preview$provider_currency, Ergebnis = preview$resulting_verification_status,
      Aktiv = if (isTRUE(preview$resulting_enabled)) "ja" else "nein",
      Providerzugriff = "nein", check.names = FALSE
    )
  }, striped = TRUE, bordered = TRUE)
  output$asset_center_provider_table <- shiny::renderTable({
    model <- asset_center_provider_catalog(); if (is.null(model)) return(data.frame())
    rows <- data_asset_center_provider_rows_v1(model, input$asset_center_asset)
    if (!length(rows)) return(data.frame())
    desktop_workflow_rows_frame_v1(lapply(rows, function(row) list(
      Verwendung = row$capability, Anbieter = pl_price_provider_label_v1(row$provider_id), Symbol = row$provider_symbol,
      Börse = if (is.null(row$exchange_code)) "—" else row$exchange_code,
      MIC = if (is.null(row$mic_code)) "—" else row$mic_code,
      Währung = row$provider_currency, Status = row$verification_status,
      Aktiv = if (isTRUE(row$enabled)) "ja" else "nein"
    )))
  }, striped = TRUE, bordered = FALSE)
  output$asset_center_provider_preview <- shiny::renderTable({
    preview <- asset_center_provider_preview(); if (is.null(preview)) return(data.frame())
    data.frame(
      Asset = preview$asset_label, Aktion = preview$action, Provider = preview$provider_id,
      Symbol = preview$provider_symbol, Währung = preview$provider_currency,
      Ergebnis = preview$resulting_verification_status, Aktiv = "nein", check.names = FALSE
    )
  }, striped = TRUE, bordered = TRUE)
  output$asset_center_tax_preview <- shiny::renderTable({
    preview <- asset_center_tax_preview(); if (is.null(preview)) return(data.frame())
    summary <- preview$summary
    data.frame(
      Feld = names(summary),
      Wert = vapply(summary, function(value) if (is.null(value)) "—" else as.character(value), character(1L)),
      check.names = FALSE, stringsAsFactors = FALSE
    )
  }, striped = TRUE, bordered = TRUE)
  output$asset_center_history_state <- shiny::renderUI({
    state_value <- asset_center_history_state()
    portelyra_status_panel(
      "Gespeicherte Historie der Tageskurse · gestufte Prüfung",
      paste("Status:", state_value, "· Plan, bestätigter Abruf, Vormerken lokal beim Eigentümer und bestätigte Veröffentlichung bleiben getrennt. Nur Fehlendes, erneuter Versuch bei Quelllücken und vollständige Aktualisierung werden nie vermischt."),
      tone = if (identical(state_value, "complete")) "positive" else "neutral"
    )
  })
  output$asset_center_history_plan_table <- shiny::renderTable({
    plan <- asset_center_market_plan(); if (is.null(plan) || !length(plan$ranges)) return(data.frame())
    desktop_workflow_rows_frame_v1(lapply(data_asset_center_history_ranges_v1(plan), function(row) list(
      Bereich = row$ref, Von = row$start_date, Bis = row$end_date,
      Kalendertage = row$calendar_day_count, Modus = plan$mode,
      Providerzugriff = "nein", Write = "nein"
    )))
  }, striped = TRUE, bordered = FALSE)
  output$asset_center_history_fetch_preview <- shiny::renderTable({
    preview <- asset_center_market_fetch_preview(); if (is.null(preview)) return(data.frame())
    data.frame(
      Von = preview$scope_start_date, Bis = preview$scope_end_date,
      Kalendertage = preview$target_day_count, Modus = preview$mode,
      `Abrufe beim Anbieter` = preview$provider_call_count,
      Providerzugriff = "erst nach Bestätigung",
      `Zwischenstand lokal` = "ja",
      `Historie wird geschrieben` = "nein",
      `Zweite Bestätigung` = "für Veröffentlichung erforderlich",
      `Erneuter Abruf beim Veröffentlichen` = "nein",
      check.names = FALSE
    )
  }, striped = TRUE, bordered = TRUE)
  output$asset_center_history_fetch_result <- shiny::renderUI({
    result <- asset_center_market_fetch_result(); if (is.null(result)) return(NULL)
    if (result$status %in% c("fetch_failed", "recovery_required")) {
      recovery <- result$recovery_result
      return(portelyra_status_panel(
        if (identical(result$status, "fetch_failed")) "Abrufversuch terminal fehlgeschlagen" else "Exakter Abgleich weiterhin erforderlich",
        paste0(
          pl_error_text_v1(recovery$code),
          if (isTRUE(recovery$provider_access_possible)) " · Ein externer Abruf kann erfolgt sein." else "",
          if (isTRUE(recovery$market_history_write_possible)) " · Eine mögliche Wirkung des Schreibvorgangs muss weiterhin gegen den exakten Beleg abgeglichen werden." else " · Es wurde kein Schreiben von Marktdaten festgestellt.",
          " · Kein automatischer neuer Versuch."
        ),
        tone = if (identical(result$status, "fetch_failed")) "neutral" else "warning"
      ))
    }
    summary <- result$review$summary
    portelyra_status_panel(
      if (identical(result$status, "published")) "Persistierte Veröffentlichung wiederhergestellt" else if (identical(result$status, "rejected")) "Verworfener Prüfvorgang wiederhergestellt" else "Abruf verbraucht · Kandidat gestagt",
      paste(
        summary$observed_candidate_count, "Beobachtungen ·", summary$non_trading_day_count,
        "Nicht-Handelstage ·", summary$source_gap_count, "Quelllücken ·",
        if (identical(result$status, "published")) "Veröffentlichungsbeleg abgeglichen." else "Keine Marktdaten geschrieben."
      ),
      tone = if (identical(result$status, "published")) "positive" else if (identical(result$status, "rejected")) "neutral" else "warning"
    )
  })
  output$asset_center_history_review_state <- shiny::renderUI({
    review <- asset_center_market_review(); if (is.null(review)) return(NULL)
    view <- tryCatch(data_market_history_review_status_v1(review), error = function(error) NULL)
    if (is.null(view)) return(portelyra_status_panel("Prüfung blockiert", "Der öffentliche Vertrag der Prüfung ist ungültig.", tone = "warning"))
    portelyra_status_panel(view$title, view$copy, tone = view$tone)
  })
  output$asset_center_history_review_summary <- shiny::renderTable({
    review <- asset_center_market_review(); if (is.null(review)) return(data.frame())
    data_market_history_review_summary_v1(review)
  }, striped = TRUE, bordered = FALSE)
  output$asset_center_history_review_plot <- shiny::renderPlot({
    review <- asset_center_market_review(); shiny::req(!is.null(review))
    data_market_history_review_plot_v1(review)
  })
  output$asset_center_history_review_table <- shiny::renderTable({
    review <- asset_center_market_review(); if (is.null(review)) return(data.frame())
    data_market_history_review_rows_v1(review)
  }, striped = TRUE, bordered = TRUE, spacing = "xs")
  output$asset_center_history_publish_result <- shiny::renderUI({
    result <- asset_center_market_publication_result(); if (is.null(result)) return(NULL)
    if (identical(result$status, "rejected")) {
      return(portelyra_status_panel(
        "Kandidat verworfen", "Kein Schreiben von Marktdaten und kein Kursabruf; dieser Kandidat kann nicht mehr veröffentlicht werden.", tone = "neutral"
      ))
    }
    portelyra_status_panel(
      "Kandidat veröffentlicht (nur fortgeschrieben)",
      paste(result$appended_day_count, "neu ·", result$corrected_day_count, "korrigiert ·", result$unchanged_day_count, "unverändert ·", result$imputed_non_trading_day_count, "kalendergebundene Ableitungen in der Prüfansicht · kein erneuter Abruf beim Kursanbieter."),
      tone = if (result$source_gap_count > 0L) "warning" else "positive"
    )
  })
  output$asset_center_summary <- shiny::renderUI({
    catalog <- asset_center_catalog(); if (is.null(catalog)) return(portelyra_status_panel("Abschluss noch nicht verfügbar", "Asset-Center zuerst aktualisieren."))
    summary <- tryCatch(data_asset_center_summary_v1(
      catalog, asset_center_provider_catalog(), input$asset_center_asset,
      asset_center_tax_state(), asset_center_history_state(), asset_center_activity_state()
    ), error = function(error) NULL)
    if (is.null(summary)) return(portelyra_status_panel("Abschluss blockiert", "Bitte ein gültiges Asset auswählen.", tone = "warning"))
    portelyra_status_panel(
      summary$title,
      if (identical(summary$state, "asset_available")) "Die realisierte Berechnung bleibt auch ohne Kursanbieter oder Steuer möglich; fehlende Dimensionen werden nicht als null ausgegeben." else "Stammdaten sind der einzige erforderliche erste Schritt.",
      tone = if (identical(summary$state, "asset_available")) "positive" else "warning"
    )
  })
  output$asset_center_summary_table <- shiny::renderTable({
    catalog <- asset_center_catalog(); if (is.null(catalog)) return(data.frame())
    summary <- tryCatch(data_asset_center_summary_v1(
      catalog, asset_center_provider_catalog(), input$asset_center_asset,
      asset_center_tax_state(), asset_center_history_state(), asset_center_activity_state()
    ), error = function(error) NULL)
    if (is.null(summary)) data.frame() else summary$progress
  }, striped = TRUE, bordered = FALSE)

  output$transaction_state <- shiny::renderUI({
    catalog <- transaction_catalog(); preview <- transaction_preview()
    if (is.null(catalog)) return(portelyra_status_panel("Auswahl nicht geladen", "Auswahl aktualisieren startet keinen Worker."))
    portelyra_status_panel(if (is.null(preview)) "Transaktionseditor bereit" else "Vorschau wartet auf Bestätigung",
                           paste(length(catalog$current_transactions), "aktuelle Transaktionen"), tone = if (is.null(preview)) "neutral" else "warning")
  })
  output$transaction_preview <- shiny::renderTable({
    preview <- transaction_preview(); if (is.null(preview)) return(data.frame())
    desktop_workflow_rows_frame_v1(preview$postings)
  }, striped = TRUE, bordered = TRUE)
  output$catalog_state <- shiny::renderUI({
    model <- catalog_model(); preview <- catalog_preview(); csv_preview <- catalog_csv_preview()
    if (is.null(model)) return(portelyra_status_panel("Stammdaten-Auswahl nicht geladen", "Lesen schreibt nichts."))
    portelyra_status_panel(
      if (!is.null(preview)) "Stammdaten-Vorschau wartet" else if (!is.null(csv_preview)) "CSV-Plan wartet" else "Stammdaten-Editor bereit",
      paste(length(model$portfolios), "Portfolios ·", length(model$accounts), "Konten ·", length(model$assets), "Assets"),
      tone = if (is.null(preview) && is.null(csv_preview)) "neutral" else "warning"
    )
  })
  output$catalog_preview <- shiny::renderTable({
    preview <- catalog_preview(); if (is.null(preview)) return(data.frame())
    data.frame(
      Aktion = preview$action, Bereich = preview$entity_type, Bezeichnung = preview$display_name,
      `Bisherige Preiswährung` = if (is.null(preview$current_price_currency)) "—" else preview$current_price_currency,
      `Neue Preiswährung` = if (is.null(preview$proposed_price_currency)) "—" else preview$proposed_price_currency,
      Status = preview$status, check.names = FALSE
    )
  }, striped = TRUE, bordered = TRUE)
  output$catalog_csv_references <- shiny::renderTable({
    model <- catalog_csv_model(); if (is.null(model) || !length(model$portfolios)) return(data.frame())
    desktop_workflow_rows_frame_v1(model$portfolios)
  }, striped = TRUE, bordered = FALSE)
  output$catalog_csv_preview <- shiny::renderTable({
    preview <- catalog_csv_preview(); if (is.null(preview) || !length(preview$rows)) return(data.frame())
    desktop_workflow_rows_frame_v1(preview$rows)
  }, striped = TRUE, bordered = TRUE)
  output$catalog_csv_template <- shiny::downloadHandler(
    filename = function() "desktop-catalog.csv",
    content = function(file) spotcore::desktop_csv_import_template_v1(file),
    contentType = "text/csv"
  )
  # Welche Assets eigene Werte tragen - mit den Feldern, die von der Vorgabe abweichen.
  output$run_evidence_list <- shiny::renderUI({
    assets <- run_evidence_assets()
    if (!length(assets)) return(portelyra_status_panel("Abschluss-Eingaben nicht geladen", "„Abschluss-Eingaben lesen“ lädt die Assets; das schreibt nichts."))
    rows <- Filter(Negate(is.null), lapply(assets, function(asset) {
      changed <- desktop_run_evidence_changed_v1(asset, run_asset_form(asset))
      if (length(changed)) shiny::tags$li(shiny::tags$strong(asset$label), ": ", paste(unname(DESKTOP_RUN_EVIDENCE_LABELS[changed]), collapse = ", "))
    }))
    if (!length(rows)) return(shiny::p(class = "pl-field-hint", sprintf("%d Assets, keines mit eigenen Werten – der Lauf nimmt überall den Bewertungsstand.", length(assets))))
    shiny::div(shiny::p(class = "pl-field-hint", sprintf("Assets mit eigenen Werten (%d von %d):", length(rows), length(assets))), shiny::tags$ul(rows))
  })
  output$run_fee_hint <- shiny::renderUI({
    source <- input$run_fee_source
    if (is.null(source)) return(NULL)
    copy <- switch(source,
      derived_from_transactions = "Je Asset aus Summe der Gebühren geteilt durch Summe der Umsätze über Käufe und Verkäufe. Ohne eigene Transaktionen gilt der Portfoliodurchschnitt; ohne jede Gebühr null Prozent, ausdrücklich benannt.",
      fixed_per_trade = "Ein Betrag in EUR je Position, unabhängig vom Umsatz. Das Feld daneben muss gefüllt sein.",
      percentage_of_turnover = "Ein Prozentsatz vom Marktwert der Position. Das Feld daneben muss gefüllt sein.")
    portelyra_status_panel("Gebührenannahme", copy, tone = "neutral")
  })
  output$run_state <- shiny::renderUI({
    state()
    status <- tryCatch(spotcore::desktop_run_center_status_v1(runtime$context), error = function(error) list(status = "unavailable", failure_code = spotcore::desktop_product_safe_error_code_v1(error), resumable = FALSE, run_label = NULL))
    portelyra_status_panel(paste("Abschluss", pl_run_status_label_v1(status$status)), if (is.null(status$failure_code)) paste("Fortsetzbar:", if (isTRUE(status$resumable)) "ja" else "nein") else pl_error_text_v1(status$failure_code), tone = if (status$status %in% c("completed", "empty")) "neutral" else "warning")
  })
  output$run_publication_status <- shiny::renderUI({
    if (!published_workflow_loaded) shiny::isolate(load_published_workflow())
    shown <- published_workflow()
    desktop_workflow_status_ui_v1(shown, if (!is.list(shown$model)) NULL else tryCatch(
      data_refresh_all_portfolio_modules_v1(project_root, runtime$context, label = shown$model$portfolio_label), error = function(error) NULL))
  })
  output$run_market_source <- shiny::renderUI({
    p<-run_preview();if(is.null(p))return(NULL)
    shiny::p(if(is.null(p$market_snapshot_source))"Run-Quelle: manuelle Markt-/FX-Eingaben"else paste("Run-Quelle: abgeschlossene EUR-Projektion ·",p$market_snapshot_source$as_of_date,"· zusätzlicher exakter Marktwertteil, kein Gesamtabschluss"))
  })
  output$run_preview <- shiny::renderTable({
    preview <- run_preview(); if (is.null(preview)) return(data.frame())
    # Ohne interne Kennung, mit deutschen Spalten und Werten (#490).
    desktop_workflow_labeled_frame_v1(lapply(preview$asset_inputs, function(row) { row$asset_id <- NULL; row }))
  }, striped = TRUE, bordered = TRUE)
  output$run_stages <- shiny::renderTable({
    state()
    preview <- run_preview()
    # Stufen, Stand und Grund in Worten wie in Datenbasis und Analyse (#490).
    stage <- function(code) vapply(code, function(item) .desktop_workflow_label_of_v1(DESKTOP_WORKFLOW_STAGE_LABELS_V1, item), character(1L), USE.NAMES = FALSE)
    if (!is.null(preview)) return(data.frame(Stufe = stage(unlist(preview$stages, use.names = FALSE)), Stand = "geplant", Grund = "", check.names = FALSE))
    status <- tryCatch(spotcore::desktop_run_center_status_v1(runtime$context), error = function(error) NULL)
    if (is.null(status) || !length(status$stage_states)) return(data.frame())
    data.frame(
      Stufe = stage(vapply(status$stage_states, `[[`, character(1L), "stage_code")),
      Stand = vapply(status$stage_states, function(row) .desktop_workflow_state_label_v1(row$status), character(1L)),
      Grund = vapply(status$stage_states, function(row) if (is.null(row$failure_code)) "" else .desktop_workflow_label_of_v1(DESKTOP_WORKFLOW_FAILURE_LABELS_V1, row$failure_code), character(1L)),
      check.names = FALSE
    )
  }, striped = TRUE, bordered = TRUE)
}

shiny::shinyApp(ui, server)
