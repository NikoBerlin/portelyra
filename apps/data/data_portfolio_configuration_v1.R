# Umfang je Portfolio (#542, Festlegungen 06.11. und 10.11.2026): Einstellungen "Umfang dieses Portfolios" und die
# gefuehrte Einrichtung in der Data-App. Kern und Pruefung: migrations/reference/portfolio_configuration_v1.py, CLI
# scripts/desktop_portfolio_configuration.py, Vertrag contracts/portfolio-configuration/v1/. Die Oberflaeche baut nur die Fassung aus
# den Haekchen, zeigt die Vorschau des Kerns mit ihren Folgen und schreibt erst nach dem Haekchen "Ich habe die Vorschau geprueft.".
#
# - Haekchen steuern, was angeboten wird und was laeuft, nicht die Rechnung. Abschalten loescht nichts.
# - Bereiche (Reiter, Karten) folgen dem wirksamen Umfang des Datenraums (output$data_module_<key>, data_visibility_v1.R): Ein Baustein
#   laeuft, sobald ein aktives Portfolio ihn nutzt. Formulare und Importe bieten an, was im gewaehlten Portfolio gewaehlt ist.
# - Nichts verschwindet still: Ein bestehendes Asset einer nicht gewaehlten Klasse bleibt bearbeitbar und traegt einen Hinweis.
# - Die Einrichtung startet fuer jedes Portfolio, das noch nicht eingerichtet ist (neu angelegt oder ohne Fassung); ihr Schrittstand
#   gilt je Portfolio fuer die Sitzung. Ein neuer Speicher im Kern entsteht dafuer nicht.

# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
data_portfolio_configuration_abort_v1 <- function(code) {
  stop(structure(class = c("spot_portfolio_configuration_error_v1", "error", "condition"), list(message = code, call = NULL, code = code)))
}

data_portfolio_configuration_error_text_v1 <- function(code) switch(as.character(code),
  portfolio_configuration_input_invalid = paste("Die Angaben zum Umfang passen nicht zusammen: Mindestens eine Assetklasse oder Cash ist zu wählen,",
    "und die Steuerprojektion braucht den Steuerbericht."),
  portfolio_configuration_store_invalid = paste("Der Speicher für den Umfang je Portfolio ist nicht lesbar oder gehört zu einem anderen Datenraum.",
    "Bitte das Backup prüfen."),
  portfolio_configuration_preview_stale = "Die Vorschau gilt nicht mehr: Der Umfang wurde inzwischen geändert. Bitte die Vorschau neu erstellen.",
  portfolio_configuration_confirmation_required = "Bitte zuerst bestätigen, dass Sie die Vorschau geprüft haben.",
  portfolio_configuration_portfolio_unknown = "Dieses Portfolio gibt es in den Stammdaten nicht. Bitte oben in „Assets pflegen“ ein Portfolio wählen.",
  "Der Umfang dieses Portfolios ist gerade nicht lesbar.")

data_portfolio_configuration_error_copy_v1 <- function(code) sprintf("%s (%s)", data_portfolio_configuration_error_text_v1(code), as.character(code))

new_data_portfolio_configuration_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_portfolio_configuration.py")
  space <- if (is.null(cli_runner)) runtime_data_space_path(context) else ""
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_portfolio_configuration_abort_v1("portfolio_configuration_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id,
                  role = "desktop_owner")
  request <- function(extra) as.character(jsonlite::toJSON(c(list(context = payload, data_space_path = space), extra), auto_unbox = TRUE,
                                                           null = "null", digits = NA))
  parse <- function(output, status = 0L) {
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || !identical(parsed$status, "completed") || !identical(as.integer(status), 0L))
      data_portfolio_configuration_abort_v1(if (is.list(parsed) && is.character(parsed$code)) parsed$code else "portfolio_configuration_store_invalid")
    parsed$result
  }
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command), stdout = TRUE, stderr = FALSE, input = request(extra)))
    status <- attr(output, "status"); parse(output, if (is.null(status)) 0L else status)
  }
  list(
    catalog = function() run("catalog", list()),
    read = function() run("read", list()),
    # `configuration`: list(classes, modules, valuation_without_market) wie data_portfolio_configuration_build_v1 sie baut.
    # `whole_history`: Wechseln die Marktdaten, stellt der Kern die bestehenden Assets ab dem ersten Tag statt ab heute um.
    preview = function(portfolio_id, configuration, origin = "owner", whole_history = FALSE) run("preview", list(portfolio_id = portfolio_id,
      configuration = configuration, origin = origin, whole_history = isTRUE(whole_history))),
    # Die Vorschau reist unveraendert zurueck; der Kern prueft ihren Abdruck und den Stand des Portfolios.
    apply = function(preview, confirmed) run("apply", list(preview = preview, confirmed = isTRUE(confirmed))))
}

.data_pc_text_v1 <- function(value) if (is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value)) value else NULL
.data_pc_readable_v1 <- function(value) is.list(value) && is.null(attr(value, "code"))
.data_pc_failed_v1 <- function(error) structure(list(), code = if (is.character(error$code) && length(error$code) == 1L) error$code else
  "portfolio_configuration_store_invalid")

# Anwendungsbereiche der Vorschlaege (06.11.2026): Sie setzen nur Haekchen und sind danach frei aenderbar.
DATA_PORTFOLIO_CONFIGURATION_PRESET_USE_V1 <- c(
  private_tax = "Privatgeschäfte: FIFO je Wallet, Haltefrist und Freigrenze – der größte Zusatznutzen, mit dem Import der Börsen-Exporte, ohne Kursabruf und ohne Cash.",
  private_performance = "wie „Steuer“, dazu Marktkurse, Verlauf, Rendite und die Steuerprojektion.",
  overview = "mehrere Institute und alle Assetklassen mit Cash, Allokation, Analysen, Steuer und Belegen.")

# Klassen in fester Reihenfolge, wie der Katalog sie fuehrt.
.data_pc_class_keys_v1 <- function(catalog) vapply(catalog$classes, function(item) as.character(item$key), character(1L))
.data_pc_module_keys_v1 <- function(catalog) vapply(catalog$modules, function(item) as.character(item$key), character(1L))

# Die Fassung aus den Haekchen, wie der Kern sie erwartet. Die Steuerprojektion gilt nur mit dem Steuerbericht; ohne Klasse und ohne
# Cash gibt es keinen Umfang. Ergebnis: list(configuration) oder list(problem).
data_portfolio_configuration_build_v1 <- function(catalog, classes, modules, valuation) {
  keys <- .data_pc_class_keys_v1(catalog)
  chosen <- keys[keys %in% as.character(unlist(classes))]
  flags <- stats::setNames(lapply(.data_pc_module_keys_v1(catalog), function(key) isTRUE(modules[[key]])), .data_pc_module_keys_v1(catalog))
  if (!isTRUE(flags$tax_report)) flags$tax_projection <- FALSE
  if (!length(chosen) && !isTRUE(flags$cash))
    return(list(problem = "Bitte mindestens eine Assetklasse wählen oder den Baustein Cash zuschalten."))
  valuations <- vapply(catalog$valuations, function(item) as.character(item$key), character(1L))
  valuation <- if (is.character(valuation) && length(valuation) == 1L && valuation %in% valuations) valuation else valuations[[1L]]
  list(configuration = list(classes = as.list(chosen), modules = flags, valuation_without_market = valuation))
}

# Formulare und Importe (#542 B.3): Was das gewaehlte Portfolio anbietet. `asset_types` NULL heisst: kein Umfang gelesen, alles wie bisher.
data_portfolio_configuration_import_kinds_v1 <- function(choices, asset_types) {
  if (is.null(asset_types)) return(choices)
  types <- as.character(unlist(asset_types))
  offered <- c(securities = any(c("equity", "etf", "fund", "bond", "derivative") %in% types), crypto = "crypto" %in% types,
               rewards = "crypto" %in% types, cash = "cash" %in% types, fx = "fx" %in% types)
  kept <- choices[vapply(unname(choices), function(kind) !kind %in% names(offered) || isTRUE(offered[[kind]]), logical(1L))]
  if (length(kept)) kept else choices
}

# Assetarten des Neuanlage-Formulars; `keep`: eine Art, die eine Vorbelegung (Import, Suche) mitbringt - sie bleibt waehlbar.
data_portfolio_configuration_asset_type_choices_v1 <- function(choices, asset_types, keep = NULL) {
  if (is.null(asset_types)) return(choices)
  kept <- choices[unname(choices) %in% c(as.character(unlist(asset_types)), as.character(keep))]
  if (length(kept)) kept else choices
}

# "Art des Assets": Cash nur mit dem Baustein Cash; Devisen stehen bei den Non-Cash-Arten.
data_portfolio_configuration_domain_choices_v1 <- function(choices, asset_types) {
  if (is.null(asset_types)) return(choices)
  types <- as.character(unlist(asset_types))
  kept <- choices[vapply(unname(choices), function(domain) if (identical(domain, "cash")) "cash" %in% types else any(types != "cash"), logical(1L))]
  if (length(kept)) kept else choices
}

# Bewertung neuer Assets (Festlegung 10.11.2026): Ohne Marktdaten gilt fuer neue Assets die Bewertung ohne Kursabruf; "Marktdaten"
# bleibt waehlbar, steht aber zuletzt und ist so gekennzeichnet. Ergebnis: list(choices, selected) oder NULL (wie bisher).
data_portfolio_configuration_valuation_choices_v1 <- function(choices, configuration) {
  if (!is.list(configuration) || !is.list(configuration$modules) || !identical(configuration$modules$market_data, FALSE)) return(NULL)
  wanted <- .data_pc_text_v1(configuration$valuation_without_market) %||% "manual"
  values <- unname(choices); labels <- names(choices)
  others <- setdiff(values, "external_market")
  ordered <- c(intersect(wanted, others), setdiff(others, wanted), intersect("external_market", values))
  labelled <- labels[match(ordered, values)]
  labelled[ordered == "external_market"] <- paste(labelled[ordered == "external_market"], "(im Umfang abgeschaltet)")
  list(choices = stats::setNames(ordered, labelled), selected = if (wanted %in% values) wanted else ordered[[1L]])
}

# Name der Klasse einer Assetart (cash und fx gehoeren zum Baustein Cash).
data_portfolio_configuration_class_label_v1 <- function(catalog, asset_type) {
  if (isTRUE(asset_type %in% c("cash", "fx"))) return("Cash und Devisen")
  hit <- Filter(function(item) isTRUE(asset_type %in% unlist(item$asset_types)), if (is.list(catalog)) catalog$classes else list())
  if (length(hit)) as.character(hit[[1L]]$label) else "Diese Klasse"
}

# Schluessel der Klasse einer Assetart (#551): fuer "Klasse dazunehmen"; cash und fx gehoeren zum Baustein Cash.
data_portfolio_configuration_class_key_v1 <- function(catalog, asset_type) {
  if (isTRUE(asset_type %in% c("cash", "fx"))) return("cash")
  hit <- Filter(function(item) isTRUE(asset_type %in% unlist(item$asset_types)), if (is.list(catalog)) catalog$classes else list())
  if (length(hit)) as.character(hit[[1L]]$key) else "other"
}

# Hinweis an einem bestehenden Asset einer nicht gewaehlten Klasse: Es bleibt sichtbar und bearbeitbar.
data_portfolio_configuration_asset_note_ui_v1 <- function(asset_type, asset_types, catalog = NULL) {
  if (is.null(asset_types) || is.null(.data_pc_text_v1(asset_type)) || asset_type %in% as.character(unlist(asset_types))) return(NULL)
  shiny::p(class = "pl-field-hint", sprintf("%s: Klasse in diesem Portfolio nicht gewählt – unter Einstellungen → Portfolio → Umfang zuschaltbar.",
    data_portfolio_configuration_class_label_v1(catalog, asset_type)), " Das Asset bleibt bearbeitbar; seine Buchungen bleiben gespeichert und sichtbar.")
}

# Unter dem Neuanlage-Formular: welche Arten angeboten werden und welche Bewertung vorbelegt ist.
data_portfolio_configuration_new_asset_note_ui_v1 <- function(entry, filtered) {
  if (!is.list(entry)) return(NULL)
  market_off <- identical(entry$configuration$modules$market_data, FALSE)
  if (!isTRUE(filtered) && !market_off) return(NULL)
  shiny::tagList(
    if (isTRUE(filtered)) shiny::p(class = "pl-field-hint", sprintf("Zur Wahl stehen die Assetarten dieses Portfolios (%s); weitere unter Einstellungen → Portfolio → Umfang.",
      .data_pc_text_v1(entry$scope_text) %||% "–")),
    if (market_off) shiny::p(class = "pl-field-hint", paste(
      "Marktdaten sind im Umfang dieses Portfolios abgeschaltet: Neue Assets werden ohne Kursabruf bewertet (vorbelegt).",
      "„Marktdaten“ bleibt wählbar; Kurse ruft Portelyra aber nur ab, solange ein Portfolio den Baustein Marktdaten nutzt.")))
}

# --- Oberflaeche ----------------------------------------------------------------------------------------------------------------

# Haekchen, Bausteine und Bewertung ohne Kursabruf; dieselben Bausteine in den Einstellungen und in der Einrichtung (`prefix`).
data_portfolio_configuration_form_ui_v1 <- function(prefix, catalog, configuration, describe_presets = FALSE) {
  id <- function(name) paste0(prefix, name)
  modules <- if (is.list(configuration$modules)) configuration$modules else list()
  shiny::tagList(
    shiny::div(class = "pl-field-group",
      shiny::strong("Vorschlag übernehmen"),
      shiny::p(class = "pl-field-hint", "Ein Vorschlag setzt nur die Häkchen darunter; danach ist alles frei änderbar. Gespeichert wird erst mit „Übernehmen“."),
      # Ein Klick meldet den Vorschlag als Ereignis (<prefix>preset); der Server setzt die Haekchen.
      shiny::div(class = "pl-editor-actions", lapply(catalog$presets, function(item)
        shiny::tags$button(type = "button", class = "btn btn-default", `data-preset` = item$key,
          onclick = sprintf("if(window.Shiny&&Shiny.setInputValue){Shiny.setInputValue('%spreset','%s',{priority:'event'});}", prefix, item$key),
          item$label))),
      if (isTRUE(describe_presets)) shiny::tags$ul(lapply(catalog$presets, function(item) shiny::tags$li(shiny::strong(item$label), ": ",
        DATA_PORTFOLIO_CONFIGURATION_PRESET_USE_V1[[item$key]] %||% "")))),
    shiny::checkboxGroupInput(id("classes"), "Assetklassen", stats::setNames(.data_pc_class_keys_v1(catalog),
      vapply(catalog$classes, function(item) as.character(item$label), character(1L))), selected = as.character(unlist(configuration$classes)), inline = TRUE),
    shiny::p(class = "pl-field-hint", "Devisen gehören zum Baustein Cash."),
    shiny::div(class = "pl-field-group",
      shiny::strong("Bausteine"),
      shiny::p(class = "pl-field-hint", paste("Immer an ist der Grundstock: Portfolio, Konten, Assets, Buchungen, FIFO, Einstand, realisierte GuV,",
        "Bestand, Datenbasis, Sicherungen und Einstellungen.")),
      lapply(catalog$modules, function(item) {
        box <- shiny::checkboxInput(id(paste0("module_", item$key)), item$label, isTRUE(modules[[item$key]]))
        text <- shiny::p(class = "pl-field-hint", sprintf("Umfasst: %s. Ohne ihn: %s.", item$includes, item$without))
        if (identical(item$requires, "tax_report")) shiny::tagList(
          shiny::conditionalPanel(sprintf("input.%smodule_tax_report", prefix), box, text),
          shiny::conditionalPanel(sprintf("!input.%smodule_tax_report", prefix),
            shiny::p(class = "pl-field-hint", sprintf("%s: wählbar, sobald der Steuerbericht zugeschaltet ist.", item$label))))
        else shiny::tagList(box, text)
      })),
    shiny::conditionalPanel(sprintf("!input.%smodule_market_data", prefix),
      shiny::radioButtons(id("valuation"), "Bewertung ohne Kursabruf (gilt für neue Assets)", stats::setNames(
        vapply(catalog$valuations, function(item) as.character(item$key), character(1L)),
        vapply(catalog$valuations, function(item) as.character(item$label), character(1L))),
        selected = .data_pc_text_v1(configuration$valuation_without_market) %||% "manual", inline = TRUE)),
    # Wechseln die Marktdaten gegenueber dem geltenden Umfang (Festlegung 10.11.2026), stellt "Uebernehmen" die bestehenden Assets mit um.
    shiny::conditionalPanel(sprintf("input.%smodule_market_data != %s", prefix, if (isTRUE(modules$market_data)) "true" else "false"),
      shiny::checkboxInput(id("whole_history"), "Ganze Historie neu (ab dem ersten Tag statt ab heute)", FALSE),
      shiny::p(class = "pl-field-hint", paste("Die bestehenden Assets dieses Portfolios werden über die Bewertung über die Zeit mit umgestellt – ab heute",
        "(die Tage davor bleiben, wie sie sind) oder mit dem Häkchen ab dem ersten Tag. Welche es sind, zeigt die Vorschau."))))
}

.data_pc_method_label_v1 <- function(method) {
  labels <- c(external_market = "Marktdaten", manual = "eigene Kurse bzw. Trade-Kurse", transaction_only = "nur Transaktionen",
              unit_value = "Einheitswert (1 je Mengeneinheit)")
  method <- .data_pc_text_v1(method)
  if (is.null(method)) "–" else if (method %in% names(labels)) labels[[method]] else method
}

# Umstellung der bestehenden Assets in der Vorschau: je Asset bisher -> neu und ab wann; was bleibt, mit Grund.
data_portfolio_configuration_switch_ui_v1 <- function(market_switch) {
  if (!is.list(market_switch) || !length(market_switch)) return(NULL)
  when <- if (isTRUE(market_switch$whole_history)) "ab dem ersten Tag" else sprintf("ab %s", pl_day_v1(market_switch$from_day))
  title <- if (identical(market_switch$direction, "off")) "Marktdaten werden abgeschaltet – Umstellung der bestehenden Assets" else
    "Marktdaten werden zugeschaltet – Umstellung der bestehenden Assets"
  rows <- c(lapply(if (is.list(market_switch$items)) market_switch$items else list(), function(item)
              list(.data_pc_text_v1(item$display_name) %||% "–", sprintf("%s → %s", .data_pc_method_label_v1(item$catalog_method_before),
                .data_pc_method_label_v1(item$catalog_method_after)), when, "wird umgestellt")),
            lapply(c(if (is.list(market_switch$kept)) market_switch$kept else list(), if (is.list(market_switch$unready)) market_switch$unready else list()),
              function(item) list(.data_pc_text_v1(item$display_name) %||% "–", "–", "–", paste("bleibt, wie es ist:", .data_pc_text_v1(item$reason) %||% "–"))))
  shiny::div(class = "pl-field-group",
    shiny::strong(title),
    if (!length(rows)) shiny::p(class = "pl-field-hint", "Kein Asset dieses Portfolios ist umzustellen.")
    else shiny::div(class = "pl-table-wrap", pl_table_v1(c("Asset", "Bewertung bisher → neu", "Ab", "Umstellung"), rows)),
    shiny::p(class = "pl-field-hint", paste("„Übernehmen“ stellt erst diese Assets um (Stammdaten, dann Bewertung über die Zeit) und übernimmt danach",
      "den Umfang – nur, wenn jedes Asset umgestellt ist. Vorhandene Kurse bleiben gespeichert.")))
}

data_portfolio_configuration_preview_ui_v1 <- function(result, prefix) {
  shiny::tagList(
    shiny::h4(class = "pl-section-title", sprintf("Vorschau: %s", .data_pc_text_v1(result$portfolio_label) %||% "–")),
    shiny::p(shiny::strong("Umfang danach: "), .data_pc_text_v1(result$scope_text) %||% "–"),
    shiny::tags$ul(class = "pl-plain-list", lapply(unlist(result$notes), function(note) shiny::tags$li(note))),
    data_portfolio_configuration_switch_ui_v1(result$market_switch),
    if (isTRUE(result$unchanged)) portelyra_status_panel("Nichts zu ändern", "Die Häkchen entsprechen dem geltenden Umfang dieses Portfolios.", tone = "neutral")
    else shiny::tagList(
      shiny::checkboxInput(paste0(prefix, "confirm"), "Ich habe die Vorschau geprüft.", FALSE),
      shiny::div(class = "pl-editor-actions", shiny::actionButton(paste0(prefix, "apply"), "Übernehmen", class = "btn-primary"))))
}

# Einstellungen: unter "Portfolios" (#547), fuer das in "Assets pflegen" gewaehlte Portfolio.
data_portfolio_configuration_ui_v1 <- function() shiny::tagList(
  shiny::tags$h3(class = "pl-section-title", "Umfang dieses Portfolios"),
  shiny::p(class = "pl-section-copy", paste("Welche Assetklassen und Bausteine Portelyra für das oben in „Assets pflegen“ gewählte Portfolio anbietet.",
    "Die Häkchen steuern, was angeboten wird und was läuft, nicht die Rechnung; abschalten löscht nichts.")),
  shiny::uiOutput("portfolio_configuration_state"),
  shiny::tags$details(class = "pl-disclosure", id = "portfolio-configuration-change",
    shiny::tags$summary("Umfang ändern"),
    shiny::uiOutput("portfolio_configuration_form"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("portfolio_configuration_preview", "Vorschau", class = "btn-default")),
    shiny::uiOutput("portfolio_configuration_preview_panel")),
  shiny::div(class = "pl-editor-actions", shiny::actionButton("portfolio_setup_restart", "Einrichtung erneut durchgehen", class = "btn-default")))

data_portfolio_configuration_state_ui_v1 <- function(entry, portfolio) {
  if (is.null(portfolio)) return(shiny::p(class = "pl-field-hint", "Zuerst oben in „Assets pflegen“ ein Portfolio wählen."))
  if (!is.null(attr(entry, "code")))
    return(portelyra_status_panel("Umfang nicht lesbar", paste(data_portfolio_configuration_error_copy_v1(attr(entry, "code")),
      "Bis dahin bietet die App „Daten“ alles an wie bisher."), tone = "warning"))
  if (!is.list(entry)) return(shiny::p(class = "pl-field-hint", "Der Umfang wird gelesen …"))
  shiny::tagList(
    shiny::p(shiny::strong(sprintf("%s: ", .data_pc_text_v1(portfolio$label) %||% "–")), .data_pc_text_v1(entry$scope_text) %||% "–"),
    if (isTRUE(entry$configured)) shiny::p(class = "pl-field-hint", sprintf("Eingerichtet%s, zuletzt geändert am %s.",
      switch(as.character(entry$origin), existing_portfolio = " (vom bisherigen Stand übernommen: alles an)", setup = " über die Einrichtung", ""),
      pl_day_v1(entry$updated_at_utc)))
    else portelyra_status_panel("Noch nicht eingerichtet", paste("Bis zur Einrichtung gilt alles; es wird nichts ausgeblendet.",
      "Die geführte Einrichtung hilft beim Wählen."), tone = "neutral"))
}

# --- Gefuehrte Einrichtung ------------------------------------------------------------------------------------------------------

DATA_PORTFOLIO_SETUP_STEPS_V1 <- c(welcome = "Willkommen", portfolio = "Portfolio", scope = "Umfang wählen",
  accounts = "Institute, Konten und Wallets", data = "Erste Daten", prices = "Kurse", protection = "Passwortschutz", done = "Abschluss")

# Die Schritte fuer einen Umfang: "Kurse" nur mit Marktdaten.
data_portfolio_setup_steps_v1 <- function(configuration) {
  steps <- names(DATA_PORTFOLIO_SETUP_STEPS_V1)
  if (is.list(configuration) && identical(configuration$modules$market_data, FALSE)) setdiff(steps, "prices") else steps
}

# Der Schritt nach bzw. vor `step`; ein Schritt, den der Umfang nicht mehr kennt (Kurse ohne Marktdaten), steht an seinem Platz in der
# vollen Reihenfolge (Kurse: zwischen "Erste Daten" und "Passwortschutz"), ein unbekannter vor "Abschluss".
data_portfolio_setup_move_v1 <- function(step, steps, by) {
  at <- match(step, steps)
  if (is.na(at)) {
    full <- names(DATA_PORTFOLIO_SETUP_STEPS_V1)
    later <- which(steps %in% full[seq_along(full) > match(step, full, nomatch = length(full) - 1L)])
    at <- (if (length(later)) min(later) else match("done", steps)) - (if (by > 0L) 1L else 0L)
  }
  steps[[max(1L, min(length(steps), at + by))]]
}

# Skript: Einstellungen oeffnen und zu `target` springen (ein <details> wird aufgeklappt) - fuer Knoepfe ausserhalb dieser Datei (#551).
# Liegt `target` in einem Unterreiter der Einstellungen (rc.440), wird erst dieser gezeigt.
.data_settings_show_pane_js_v1 <- function(target) paste0("var t=document.getElementById('", target, "');var pane=t&&t.closest('.tab-pane');",
  "if(pane&&!pane.classList.contains('active')){var a=document.querySelector('#settings-panel a[data-toggle=\"tab\"][href=\"#'+pane.id+'\"]');",
  "if(a&&window.jQuery){jQuery(a).tab('show');}}")
data_settings_open_target_js_v1 <- function(target) paste0("var p=document.getElementById('settings-panel');if(p&&p.hasAttribute('hidden')){document.getElementById('settings_toggle').click();}",
  .data_settings_show_pane_js_v1(target),
  "setTimeout(function(){var t=document.getElementById('", target, "');if(t){if(t.tagName==='DETAILS')t.open=true;t.scrollIntoView({behavior:'smooth',block:'start'});}},150);")

# Ein Knopf, der einen vorhandenen Bereich oeffnet (Reiter, Unterreiter oder die Einstellungen) - ein Klick, kein Serverweg.
.data_pc_jump_v1 <- function(label, step = NULL, tabset = NULL, value = NULL, settings_target = NULL, refresh = FALSE) {
  script <- if (isTRUE(refresh)) "var r=document.getElementById('refresh-all-panel');if(r&&r.hasAttribute('hidden')){document.getElementById('refresh_all_toggle').click();}"
  else if (!is.null(settings_target)) paste0("var p=document.getElementById('settings-panel');if(p&&p.hasAttribute('hidden')){document.getElementById('settings_toggle').click();}",
    .data_settings_show_pane_js_v1(settings_target),
    "var t=document.getElementById('", settings_target, "');if(t){if(t.tagName==='DETAILS')t.open=true;t.scrollIntoView({behavior:'smooth',block:'start'});}")
  else paste0("$('#asset_center_step a[data-value=\"", step, "\"]').tab('show');",
    if (!is.null(tabset)) paste0("setTimeout(function(){$('#", tabset, " a[data-value=\"", value, "\"]').tab('show');",
      "var t=document.getElementById('", tabset, "');if(t){t.scrollIntoView({behavior:'smooth',block:'start'});}},0);") else "")
  shiny::tags$button(type = "button", class = "btn btn-default", onclick = script, label)
}

data_portfolio_setup_ui_v1 <- function() shiny::uiOutput("portfolio_setup_card")

data_portfolio_setup_step_ui_v1 <- function(step, portfolio, entry, catalog, documents = TRUE) {
  configuration <- if (is.list(entry)) entry$configuration else NULL
  switch(step,
    welcome = shiny::tagList(
      shiny::p("Portelyra führt Ihr Portfolio auf diesem Rechner: Buchungen, Bestände, FIFO und realisierte Gewinne – auf Wunsch mit Cash,",
        "Kursen, Verlauf, Steuerbericht und dem Import aus Belegen und Auszügen. Was Sie brauchen, wählen Sie im dritten Schritt."),
      shiny::tags$ul(
        shiny::tags$li("Lokal: Die Daten bleiben in Ihrem Datenraum auf diesem Rechner. Für Kurse greift Portelyra nur mit dem Baustein Marktdaten aufs Netz."),
        shiny::tags$li("Keine Anlageberatung: Portelyra zeigt und rechnet, es empfiehlt nichts."),
        shiny::tags$li("Ohne Gewähr: Die Steuerrechnung ist eine Modellrechnung; maßgeblich bleiben die Bescheinigungen der Institute und der Steuerbescheid.")),
      shiny::p(class = "pl-field-hint", "Jeder Schritt lässt sich überspringen; „Später fortsetzen“ merkt sich den Schritt für diese Sitzung.")),
    portfolio = shiny::tagList(
      shiny::p(sprintf("Portfolio „%s“ · Währung %s.", .data_pc_text_v1(portfolio$label) %||% "–", .data_pc_text_v1(portfolio$base_currency) %||% "–")),
      shiny::p("Ein Portfolio ist ein eigener, getrennter Bestand – etwa je steuerliche Person. Umbenennen oder ein weiteres anlegen geht in den",
        "Einstellungen unter „Portfolio“ → „Portfolios“; die Währung steht beim Anlegen fest."),
      shiny::div(class = "pl-editor-actions", .data_pc_jump_v1("Einstellungen · Portfolios öffnen", settings_target = "asset-center-portfolio-inline"))),
    scope = shiny::tagList(
      shiny::p("Wählen Sie, was dieses Portfolio umfasst. Die Häkchen steuern, was angeboten wird und was läuft – nicht die Rechnung. Abschalten löscht",
        "nichts; zuschalten geht jederzeit in den Einstellungen unter „Portfolio“ → „Umfang dieses Portfolios“."),
      if (is.list(catalog) && is.list(configuration)) shiny::tagList(
        data_portfolio_configuration_form_ui_v1("portfolio_setup_scope_", catalog, configuration, describe_presets = TRUE),
        shiny::div(class = "pl-editor-actions", shiny::actionButton("portfolio_setup_scope_preview", "Vorschau", class = "btn-default")),
        shiny::uiOutput("portfolio_setup_scope_preview_panel"))
      else portelyra_status_panel("Umfang nicht lesbar", "Die Bausteine ließen sich nicht lesen. Diesen Schritt überspringen und später in den Einstellungen wählen.",
        tone = "warning")),
    accounts = shiny::tagList(
      shiny::p("Legen Sie die Institute und Börsen an, bei denen Sie Konten führen, dazu je Depot, Bankkonto oder Wallet ein Konto. Ein neues Institut",
        "entsteht mit dem ersten Konto: seinen Namen ins Feld „Institut / Börse“ tippen."),
      shiny::div(class = "pl-editor-actions", .data_pc_jump_v1("Zu „Konten und Institute“", step = "1 · Stammdaten", tabset = "master_section", value = "accounts"))),
    # Ohne den Baustein Belege (#583) gibt es Import und Eingang nicht: dann nur der Weg von Hand und wo der Import zugeschaltet wird.
    data = shiny::tagList(
      if (isTRUE(documents)) shiny::tagList(
        shiny::p("Erste Buchungen kommen aus Belegen und Exporten der Institute (Import) oder von Hand. Der Import prüft zuerst und schreibt nichts;",
          "gebucht wird nur Neues, mit den Beträgen des Belegs."),
        shiny::p(class = "pl-field-hint", "Belegordner je Institut legen Sie im „Eingang“ an und buchen von dort aus."))
      else shiny::p("Erste Buchungen erfassen Sie von Hand. Den Import aus Belegen und Auszügen schalten Sie in den Einstellungen unter",
        "„Portfolio“ → „Umfang dieses Portfolios“ zu."),
      shiny::div(class = "pl-editor-actions",
        if (isTRUE(documents)) .data_pc_jump_v1("Zum Import", step = "transactions", tabset = "transactions_view", value = "import"),
        .data_pc_jump_v1("Von Hand erfassen", step = "transactions", tabset = "transactions_view", value = "manual"))),
    prices = shiny::tagList(
      shiny::p("Kurse kommen von einem Kursanbieter (Vorgabe: Yahoo Finance); welche Anbieter aktiv sind, steht im Reiter „Kursanbieter“.",
        "„Alles aktualisieren“ (links) ruft fehlende Kurse ab und bringt alle Ergebnisse auf den neuesten Stand; in den Einstellungen lässt sich",
        "dafür ein Zeitplan festlegen."),
      shiny::div(class = "pl-editor-actions",
        .data_pc_jump_v1("Zu den Kursanbietern", step = "transactions", tabset = "transactions_view", value = "price_providers"),
        .data_pc_jump_v1("„Alles aktualisieren“ öffnen", refresh = TRUE))),
    protection = shiny::tagList(
      shiny::p("Auf Wunsch verschlüsselt Portelyra den ganzen Datenbestand – alle Portfolios – und die Backups mit einem Passwort. Ohne Passwort",
        "ist dann nichts lesbar, auch nicht in Kopien auf einer Sicherungsplatte. Beim Einrichten zeigt Portelyra einmal einen",
        "Wiederherstellungsschlüssel für den Fall, dass das Passwort vergessen wird."),
      shiny::p(class = "pl-field-hint", "Vorerst nur unter Linux. Einrichten und wieder ansehen in den Einstellungen unter „Sicherheit und Speicher“ → „Passwortschutz“; der Schritt lässt sich überspringen."),
      shiny::div(class = "pl-editor-actions", .data_pc_jump_v1("Einstellungen · Passwortschutz öffnen", settings_target = "data-protection-card"))),
    done = shiny::tagList(
      shiny::p("Geschafft. Wo was zu finden ist:"),
      shiny::tags$ul(
        shiny::tags$li("Daten (hier): Buchungen, Importe, Stammdaten, Kurse und Einstellungen – hier wird geschrieben."),
        shiny::tags$li("Cockpit: Grundlagen, Herkunft und Konfiguration – nur lesend."),
        shiny::tags$li("Analyse: Bestand, Stichtage und, mit „Verlauf und Analyse“, Verlauf und Rendite."),
        shiny::tags$li("Steuer: Berichte je Jahr – mit dem Baustein Steuerbericht.")),
      shiny::p(class = "pl-field-hint", paste("Das Handbuch liegt im Programmordner unter docs/handbuch (etwa „Monatlicher Eingang“ und „Steuer: was das Regelmodul",
        "abdeckt“). Diese Einrichtung lässt sich in den Einstellungen unter „Portfolio“ → „Umfang dieses Portfolios“ erneut durchgehen."))),
    NULL)
}

data_portfolio_setup_card_ui_v1 <- function(step, steps, portfolio, body) {
  at <- match(step, steps); last <- identical(step, "done")
  portelyra_card(sprintf("Einrichtung · Portfolio „%s“", .data_pc_text_v1(portfolio$label) %||% "–"),
    copy = sprintf("Schritt %d von %d: %s", at, length(steps), DATA_PORTFOLIO_SETUP_STEPS_V1[[step]]),
    class = "pl-portfolio-setup",
    shiny::tags$ol(class = "pl-steps", style = "display:flex;flex-wrap:wrap;gap:6px 18px;padding-left:18px;margin:4px 0 14px;font-size:.82rem",
      lapply(seq_along(steps), function(index) shiny::tags$li(`aria-current` = if (index == at) "step" else NULL,
        style = if (index == at) "font-weight:750" else "color:var(--pl-muted)", DATA_PORTFOLIO_SETUP_STEPS_V1[[steps[[index]]]]))),
    body,
    shiny::div(class = "pl-editor-actions",
      if (at > 1L) shiny::actionButton("portfolio_setup_back", "Zurück", class = "btn-default"),
      if (!last) shiny::actionButton("portfolio_setup_next", "Weiter", class = "btn-primary"),
      if (!last) shiny::actionButton("portfolio_setup_skip", "Überspringen", class = "btn-default"),
      if (last) shiny::actionButton("portfolio_setup_finish", "Fertig", class = "btn-primary")
      else shiny::actionButton("portfolio_setup_later", "Später fortsetzen", class = "btn-default")))
}

# --- Server ---------------------------------------------------------------------------------------------------------------------

# Vorschau, Haekchen und Uebernehmen fuer eine Fassung - in den Einstellungen (`origin` owner) und in der Einrichtung (setup).
.data_pc_editor_v1 <- function(input, output, session, service, prefix, origin, entry, portfolio, catalog, form_output, after_apply,
    active = shiny::reactive(TRUE), switcher = NULL, request = NULL) {
  id <- function(name) paste0(prefix, name)
  preview <- shiny::reactiveVal(NULL)   # list(key, result)
  feedback <- shiny::reactiveVal(NULL)  # list(tone, title, copy)
  # Das Formular baut sich nur neu, wenn Portfolio oder geltende Fassung wechseln - nicht bei jedem Neulesen der Stammdaten, sonst
  # sprangen gerade gesetzte Haekchen zurueck.
  basis <- shiny::reactiveVal(NULL)
  shiny::observe({
    current <- entry(); chosen <- portfolio()
    key <- if (.data_pc_readable_v1(current) && is.list(current$configuration) && is.list(chosen))
      paste(chosen$portfolio_id, jsonlite::toJSON(current$configuration, auto_unbox = TRUE)) else NULL
    if (!identical(key, shiny::isolate(basis())$key)) basis(list(key = key, configuration = if (is.null(key)) NULL else current$configuration))
  })
  # Gebaut (und der Katalog gelesen) wird erst, wenn die Einstellungen offen sind; danach bleibt das Formular stehen.
  opened <- shiny::reactiveVal(FALSE)
  shiny::observe(if (isTRUE(active())) opened(TRUE))
  if (!is.null(form_output)) output[[form_output]] <- shiny::renderUI({
    if (!isTRUE(opened())) return(NULL)
    state <- basis(); items <- catalog()
    if (!is.list(state$configuration)) return(shiny::p(class = "pl-field-hint", "Zuerst oben in „Assets pflegen“ ein Portfolio wählen."))
    if (!is.list(items)) return(portelyra_status_panel("Bausteine nicht lesbar", data_portfolio_configuration_error_copy_v1("portfolio_configuration_store_invalid"), tone = "warning"))
    configuration <- state$configuration
    # "Klasse dazunehmen" aus einem Import (#551): die Klasse vorangekreuzt; uebernommen wird wie immer erst ueber die Vorschau.
    wanted <- if (is.function(request)) request()$keys else NULL
    if (length(wanted)) configuration$classes <- as.list(union(as.character(unlist(configuration$classes)), wanted))
    data_portfolio_configuration_form_ui_v1(prefix, items, configuration)
  })
  if (is.function(request)) shiny::observeEvent(request(), {
    wanted <- request()$keys; if (!length(wanted)) return()
    current <- input[[id("classes")]]
    if (!is.null(current)) shiny::updateCheckboxGroupInput(session, id("classes"), selected = union(as.character(current), wanted))
  }, ignoreInit = TRUE)
  # Vorschlaege setzen nur Haekchen.
  shiny::observeEvent(input[[id("preset")]], {
    items <- catalog(); wanted <- input[[id("preset")]]
    hit <- Filter(function(item) identical(item$key, wanted), if (is.list(items)) items$presets else list())
    if (!length(hit)) return()
    configuration <- hit[[1L]]$configuration
    shiny::updateCheckboxGroupInput(session, id("classes"), selected = as.character(unlist(configuration$classes)))
    for (key in names(configuration$modules)) shiny::updateCheckboxInput(session, id(paste0("module_", key)), value = isTRUE(configuration$modules[[key]]))
    shiny::updateRadioButtons(session, id("valuation"), selected = configuration$valuation_without_market)
  })
  # Ohne Steuerbericht keine Steuerprojektion: Das Haekchen geht mit aus.
  shiny::observeEvent(input[[id("module_tax_report")]], {
    if (identical(input[[id("module_tax_report")]], FALSE) && isTRUE(input[[id("module_tax_projection")]]))
      shiny::updateCheckboxInput(session, id("module_tax_projection"), value = FALSE)
  }, ignoreInit = TRUE)
  # Ohne den Katalog: Die Bausteine kennt auch data_visibility_v1.R; so liest der Start den Katalog nicht.
  inputs <- shiny::reactive({
    keys <- DATA_MODULES_V1
    list(portfolio = portfolio()$portfolio_id, classes = sort(as.character(unlist(input[[id("classes")]]))),
         modules = stats::setNames(lapply(keys, function(key) isTRUE(input[[id(paste0("module_", key))]])), keys), valuation = input[[id("valuation")]],
         whole_history = isTRUE(input[[id("whole_history")]]))
  })
  # Die Vorschau gilt nur fuer genau die Angaben, mit denen sie erstellt wurde.
  shiny::observeEvent(inputs(), {
    current <- shiny::isolate(preview())
    if (is.list(current) && !identical(current$key, inputs())) { preview(NULL); feedback(NULL) }
  }, ignoreInit = TRUE)
  shiny::observeEvent(input[[id("preview")]], {
    preview(NULL); feedback(NULL)
    chosen <- portfolio(); items <- catalog()
    if (!is.list(chosen)) return(feedback(list(tone = "warning", title = "Keine Vorschau", copy = "Zuerst oben in „Assets pflegen“ ein Portfolio wählen.")))
    if (!is.list(items)) return(feedback(list(tone = "warning", title = "Keine Vorschau", copy = data_portfolio_configuration_error_copy_v1("portfolio_configuration_store_invalid"))))
    key <- inputs()
    built <- data_portfolio_configuration_build_v1(items, key$classes, key$modules, key$valuation)
    if (!is.null(built$problem)) return(feedback(list(tone = "warning", title = "Keine Vorschau", copy = built$problem)))
    # "Ganze Historie neu" zaehlt nur, wenn die Marktdaten wechseln (dann stellt der Kern die bestehenden Assets mit um).
    current <- entry()
    switching <- .data_pc_readable_v1(current) && is.list(current$configuration) &&
      !identical(isTRUE(current$configuration$modules$market_data), isTRUE(key$modules$market_data))
    result <- if (is.null(service)) structure(list(), code = "portfolio_configuration_store_invalid") else
      tryCatch(service$preview(chosen$portfolio_id, built$configuration, origin, whole_history = switching && isTRUE(key$whole_history)), error = .data_pc_failed_v1)
    if (!.data_pc_readable_v1(result)) return(feedback(list(tone = "warning", title = "Keine Vorschau", copy = data_portfolio_configuration_error_copy_v1(attr(result, "code")))))
    preview(list(key = key, result = result))
  })
  output[[id("preview_panel")]] <- shiny::renderUI({
    current <- preview(); note <- feedback()
    shiny::tagList(if (is.list(current)) data_portfolio_configuration_preview_ui_v1(current$result, prefix),
                   if (is.list(note)) portelyra_status_panel(note$title, note$copy, tone = note$tone))
  })
  shiny::observeEvent(input[[id("apply")]], {
    current <- preview(); if (!is.list(current)) return()
    if (!isTRUE(input[[id("confirm")]])) return(feedback(list(tone = "warning", title = "Nicht übernommen",
      copy = data_portfolio_configuration_error_copy_v1("portfolio_configuration_confirmation_required"))))
    preview(NULL)
    # Wechseln die Marktdaten (Festlegung 10.11.2026), stellt dieselbe Bestaetigung zuerst die bestehenden Assets um - je Asset wie
    # die Karte "Bewertung ueber die Zeit". Der Umfang gilt erst, wenn jedes Asset umgestellt ist.
    switched <- data_portfolio_configuration_switch_assets_v1(current$result$market_switch, switcher)
    if (length(switched$done) || length(switched$partial)) tryCatch(switcher$assets_changed(), error = function(error) NULL)
    if (length(switched$failed) || length(switched$partial)) return(feedback(list(tone = "error", title = "Umfang noch nicht übernommen",
      copy = data_portfolio_configuration_switch_report_ui_v1(switched, held = TRUE))))
    applied <- if (is.null(service)) structure(list(), code = "portfolio_configuration_store_invalid") else
      tryCatch(service$apply(current$result, TRUE), error = .data_pc_failed_v1)
    if (!.data_pc_readable_v1(applied)) return(feedback(list(tone = "error", title = "Nicht übernommen", copy = shiny::tagList(
      data_portfolio_configuration_error_copy_v1(attr(applied, "code")),
      if (length(switched$done)) data_portfolio_configuration_switch_report_ui_v1(switched, held = TRUE)))))
    after_apply()
    feedback(list(tone = if (identical(applied$display_settings, "failed")) "warning" else "positive", title = "Umfang übernommen", copy = shiny::tagList(paste0(
      sprintf("Umfang jetzt: %s. ", .data_pc_text_v1(applied$scope_text) %||% "–"),
      "Die App „Daten“ bietet ab jetzt an, was gewählt ist; Abläufe richten sich beim nächsten Lauf danach. Gelöscht wurde nichts.",
      if (identical(applied$display_settings, "failed")) " Die Einstellungen der Anzeige-Apps ließen sich nicht neu veröffentlichen; sie folgen mit dem nächsten „Alles aktualisieren“." else ""),
      if (length(switched$done)) data_portfolio_configuration_switch_report_ui_v1(switched, held = FALSE))))
  })
  invisible(list(preview = preview, feedback = feedback, inputs = inputs))
}

# Die Umstellung der bestehenden Assets beim Wechsel der Marktdaten (Festlegung 10.11.2026), je Eintrag des Kerns wie die Karte
# "Bewertung ueber die Zeit": Vorschau der Zeitleiste mit den fertigen Abschnitten; weicht die Bewertungsart der Stammdaten ab, zuerst
# der Katalogbefehl, dann die Zeitleiste. Ein Fehler haelt die uebrigen nicht auf. `switcher`: list(timeline (Dienst der Zeitleiste),
# catalog_revise(method, asset_id), assets_changed()). Ergebnis: done (umgestellt), partial (nur Stammdaten), failed - je mit Grund.
data_portfolio_configuration_switch_assets_v1 <- function(market_switch, switcher) {
  result <- list(done = list(), partial = list(), failed = list())
  items <- if (is.list(market_switch) && is.list(market_switch$items)) market_switch$items else list()
  if (!length(items)) return(result)
  code_of <- function(error, fallback) if (is.character(error$code) && length(error$code) == 1L) error$code else fallback
  for (item in items) {
    name <- .data_pc_text_v1(item$display_name) %||% "–"
    if (!is.list(switcher) || is.null(switcher$timeline) || !is.function(switcher$catalog_revise)) {
      result$failed[[length(result$failed) + 1L]] <- list(name = name, stage = "timeline", code = "asset_valuation_timeline_store_invalid"); next
    }
    planned <- tryCatch(switcher$timeline$preview(item$asset_id, item$segments), error = function(error) structure(list(),
      code = code_of(error, "asset_valuation_timeline_store_invalid")))
    if (!.data_pc_readable_v1(planned)) {
      result$failed[[length(result$failed) + 1L]] <- list(name = name, stage = "timeline", code = attr(planned, "code")); next
    }
    revised <- FALSE
    if (isTRUE(planned$catalog_method_change)) {
      outcome <- tryCatch({ switcher$catalog_revise(planned$catalog_method_after, item$asset_id); TRUE },
        error = function(error) code_of(error, "desktop_catalog_boundary_failed"))
      if (!isTRUE(outcome)) { result$failed[[length(result$failed) + 1L]] <- list(name = name, stage = "catalog", code = outcome); next }
      revised <- TRUE
    }
    applied <- tryCatch(switcher$timeline$apply(planned, TRUE), error = function(error) structure(list(),
      code = code_of(error, "asset_valuation_timeline_store_invalid")))
    if (!.data_pc_readable_v1(applied)) {
      bucket <- if (revised) "partial" else "failed"
      result[[bucket]][[length(result[[bucket]]) + 1L]] <- list(name = name, stage = "timeline", code = attr(applied, "code")); next
    }
    result$done[[length(result$done) + 1L]] <- list(name = name, after = item$catalog_method_after)
  }
  result
}

.data_pc_reason_v1 <- function(row) {
  if (identical(row$stage, "catalog")) return(if (exists("data_asset_valuation_timeline_catalog_copy_v1", mode = "function"))
    paste("Bewertungsart der Stammdaten nicht umgestellt:", data_asset_valuation_timeline_catalog_copy_v1(row$code)) else
    sprintf("Bewertungsart der Stammdaten nicht umgestellt (%s)", row$code))
  if (exists("data_asset_valuation_timeline_error_copy_v1", mode = "function")) data_asset_valuation_timeline_error_copy_v1(row$code) else
    sprintf("Bewertung über die Zeit nicht gespeichert (%s)", row$code)
}

# Was beim Wechsel der Marktdaten umgestellt ist und was nicht, mit Grund und Code. `held`: der Umfang gilt (noch) nicht.
data_portfolio_configuration_switch_report_ui_v1 <- function(switched, held) {
  names_of <- function(rows) paste(vapply(rows, function(row) row$name, character(1L)), collapse = ", ")
  shiny::tagList(
    if (isTRUE(held)) shiny::p(paste("Der Umfang gilt noch nicht. Bitte die Vorschau erneut erstellen und prüfen; schon umgestellte Assets erscheinen",
      "darin nicht mehr, offene werden erneut versucht.")),
    shiny::tags$ul(class = "pl-plain-list",
      if (length(switched$done)) shiny::tags$li(sprintf("Umgestellt (%d): %s.", length(switched$done), names_of(switched$done))),
      lapply(switched$partial, function(row) shiny::tags$li(sprintf("%s: nur die Bewertungsart der Stammdaten umgestellt, die Zeitleiste nicht – %s",
        row$name, .data_pc_reason_v1(row)))),
      lapply(switched$failed, function(row) shiny::tags$li(sprintf("%s: nicht umgestellt – %s", row$name, .data_pc_reason_v1(row))))))
}

# `portfolio`: reaktiv das in "Assets pflegen" gewaehlte Portfolio als list(portfolio_id, label, base_currency) oder NULL.
# `portfolios_key`: reaktiv eine Kennung der Portfolios der Stammdaten (Kennung und Zustand). Gelesen wird, sobald sie da ist und
# wann immer sie sich aendert - beim Start, nach dem Anlegen und nach dem Archivieren eines Portfolios; der Kern legt beim ersten
# Lesen den Bestandseintrag an. `on_changed()`: nach dem Uebernehmen (etwa Formulare neu filtern). `settings_open`: das Formular der
# Einstellungen entsteht (und der Katalog wird gelesen) erst, wenn die Einstellungen offen sind. `switcher`: stellt beim Wechsel der
# Marktdaten die bestehenden Assets um (data_portfolio_configuration_switch_assets_v1).
data_portfolio_configuration_server_v1 <- function(input, output, session, service, portfolio = shiny::reactive(NULL),
    portfolios_key = shiny::reactive(NULL), on_changed = NULL, settings_open = shiny::reactive(TRUE), switcher = NULL) {
  loaded <- shiny::reactiveVal(NULL)    # Ergebnis von read oder structure(list(), code)
  read_key <- NULL
  # Die Auswahl wird bei jedem Neulesen der Stammdaten neu berechnet; als reactiveVal loest nur ein echter Wechsel etwas aus (sonst
  # baute sich das Formular neu und gerade gesetzte Haekchen sprangen zurueck).
  chosen_portfolio <- shiny::reactiveVal(NULL)
  given_portfolio <- portfolio
  shiny::observe(chosen_portfolio(tryCatch(given_portfolio(), error = function(error) NULL)), priority = 10)
  portfolio <- function() chosen_portfolio()
  cache <- new.env(parent = emptyenv())
  read <- function() {
    value <- if (is.null(service)) structure(list(), code = "portfolio_configuration_store_invalid") else tryCatch(service$read(), error = .data_pc_failed_v1)
    loaded(value)
    invisible(value)
  }
  shiny::observeEvent(portfolios_key(), {
    key <- portfolios_key()
    if (identical(key, read_key)) return()
    read_key <<- key; read()
  }, ignoreNULL = TRUE)
  # Der Katalog (Klassen, Bausteine, Vorschlaege mit Texten) aendert sich nicht; einmal je Sitzung, erst wenn ihn jemand braucht.
  catalog <- shiny::reactive({
    if (is.null(cache$catalog) && !is.null(service)) cache$catalog <- tryCatch(service$catalog(), error = function(error) NULL)
    cache$catalog
  })
  entry <- shiny::reactive({
    state <- loaded(); chosen <- portfolio()
    if (!is.list(chosen) || is.null(.data_pc_text_v1(chosen$portfolio_id))) return(NULL)
    if (!.data_pc_readable_v1(state)) return(state)
    hit <- Filter(function(item) identical(item$portfolio_id, chosen$portfolio_id), state$portfolios)
    if (length(hit)) hit[[1L]] else NULL
  })
  # Was das gewaehlte Portfolio anbietet; NULL ohne gelesenen Umfang (dann alles wie bisher).
  asset_types <- shiny::reactive({ current <- entry(); if (.data_pc_readable_v1(current) && length(current)) as.character(unlist(current$asset_types)) else NULL })
  configuration <- shiny::reactive({ current <- entry(); if (.data_pc_readable_v1(current) && length(current)) current$configuration else NULL })
  effective <- shiny::reactive({ state <- loaded(); if (.data_pc_readable_v1(state) && is.list(state$effective)) state$effective$modules else NULL })
  for (module in DATA_MODULES_V1) local({
    key <- module; output_id <- paste0("data_module_", key)
    output[[output_id]] <- shiny::renderText({ modules <- effective(); if (is.list(modules) && identical(modules[[key]], FALSE)) "off" else "on" })
    shiny::outputOptions(output, output_id, suspendWhenHidden = FALSE)
  })
  changed <- function() {
    read()
    if (is.function(on_changed)) tryCatch(on_changed(), error = function(error) NULL)
  }
  output$portfolio_configuration_state <- shiny::renderUI(data_portfolio_configuration_state_ui_v1(entry(), portfolio()))
  class_request <- shiny::reactiveVal(NULL)
  .data_pc_editor_v1(input, output, session, service, "portfolio_configuration_", "owner", entry, portfolio, catalog, "portfolio_configuration_form", changed,
    active = settings_open, switcher = switcher, request = class_request)
  setup_editor <- .data_pc_editor_v1(input, output, session, service, "portfolio_setup_scope_", "setup", entry, portfolio, catalog, NULL, changed,
    switcher = switcher)

  # Gefuehrte Einrichtung: Schrittstand je Portfolio fuer die Sitzung - list(<portfolio_id> = list(step, open)).
  progress <- shiny::reactiveVal(list())
  set_progress <- function(portfolio_id, step = NULL, open = NULL) {
    all <- shiny::isolate(progress()); current <- all[[portfolio_id]] %||% list(step = "welcome", open = FALSE)
    if (!is.null(step)) current$step <- step
    if (!is.null(open)) current$open <- open
    all[[portfolio_id]] <- current; progress(all)
  }
  # Startet von selbst fuer ein Portfolio, das noch nicht eingerichtet ist (auch gleich nach dem Anlegen), einmal je Sitzung.
  shiny::observe({
    current <- entry(); chosen <- portfolio()
    if (!.data_pc_readable_v1(current) || !length(current) || isTRUE(current$configured) || !is.list(chosen)) return()
    if (is.null(shiny::isolate(progress())[[chosen$portfolio_id]])) set_progress(chosen$portfolio_id, "welcome", TRUE)
  })
  steps <- shiny::reactive(data_portfolio_setup_steps_v1(configuration()))
  current_step <- shiny::reactive({
    chosen <- portfolio(); if (!is.list(chosen)) return(NULL)
    state <- progress()[[chosen$portfolio_id]]; if (is.null(state)) return(NULL)
    list(step = if (state$step %in% steps()) state$step else data_portfolio_setup_move_v1(state$step, steps(), 1L), open = isTRUE(state$open))
  })
  move <- function(by) {
    chosen <- portfolio(); state <- current_step(); if (!is.list(chosen) || is.null(state)) return()
    set_progress(chosen$portfolio_id, data_portfolio_setup_move_v1(state$step, steps(), by), TRUE)
  }
  shiny::observeEvent(input$portfolio_setup_next, move(1L))
  shiny::observeEvent(input$portfolio_setup_skip, move(1L))
  shiny::observeEvent(input$portfolio_setup_back, move(-1L))
  shiny::observeEvent(input$portfolio_setup_later, { chosen <- portfolio(); if (is.list(chosen)) set_progress(chosen$portfolio_id, open = FALSE) })
  shiny::observeEvent(input$portfolio_setup_finish, { chosen <- portfolio(); if (is.list(chosen)) set_progress(chosen$portfolio_id, "welcome", FALSE) })
  shiny::observeEvent(input$portfolio_setup_resume, { chosen <- portfolio(); if (is.list(chosen)) set_progress(chosen$portfolio_id, open = TRUE) })
  shiny::observeEvent(input$portfolio_setup_restart, {
    chosen <- portfolio(); if (!is.list(chosen)) return()
    set_progress(chosen$portfolio_id, "welcome", TRUE)
    session$sendCustomMessage("pl_settings_done", list(text = "Einrichtung geöffnet – oben über „Assets pflegen“."))
  })
  output$portfolio_setup_card <- shiny::renderUI({
    chosen <- portfolio(); state <- current_step(); current <- entry()
    if (!is.list(chosen) || is.null(state)) return(NULL)
    if (!state$open) {
      if (!.data_pc_readable_v1(current) || !length(current) || isTRUE(current$configured)) return(NULL)
      return(shiny::div(class = "pl-editor-actions", portelyra_status_panel(sprintf("Portfolio „%s“ ist noch nicht eingerichtet", .data_pc_text_v1(chosen$label) %||% "–"),
        "Bis dahin gilt alles; es wird nichts ausgeblendet.", tone = "neutral"),
        shiny::actionButton("portfolio_setup_resume", "Einrichtung fortsetzen", class = "btn-default")))
    }
    items <- if (identical(state$step, "scope")) catalog() else NULL
    documents <- !identical(configuration()$modules$documents, FALSE)
    data_portfolio_setup_card_ui_v1(state$step, steps(), chosen, data_portfolio_setup_step_ui_v1(state$step, chosen,
      if (.data_pc_readable_v1(current)) current else NULL, items, documents = documents))
  })
  invisible(list(read = read, state = loaded, entry = entry, configuration = configuration, asset_types = asset_types, effective = effective,
                 catalog = catalog, progress = progress, current_step = current_step, setup_editor = setup_editor, portfolio = portfolio,
                 # "Klasse dazunehmen" (#551): Klassen im Formular "Umfang dieses Portfolios" vorankreuzen.
                 request_classes = function(keys) class_request(list(keys = as.character(keys), at = as.numeric(Sys.time())))))
}

# Das in "Assets pflegen" gewaehlte Portfolio aus dem Katalog-Editor: Kennung, Name, Waehrung. Der Editor fuehrt die Kennungen
# serverseitig; in den Browser geht nur die Referenz der Auswahl.
data_portfolio_configuration_portfolio_v1 <- function(editor, ref) {
  maps <- tryCatch(editor$catalog$maps$portfolio, error = function(error) NULL)
  if (!is.list(maps) || is.null(.data_pc_text_v1(ref)) || is.null(maps[[ref]])) return(NULL)
  row <- maps[[ref]]
  if (is.null(.data_pc_text_v1(row$portfolio_id))) return(NULL)
  list(portfolio_id = row$portfolio_id, label = .data_pc_text_v1(row$display_name) %||% row$portfolio_id, base_currency = row$base_currency)
}

# Kennung der Portfolios (Kennung und Zustand): Aendert sie sich, liest die Data-App den Umfang neu.
data_portfolio_configuration_key_v1 <- function(editor) {
  maps <- tryCatch(editor$catalog$maps$portfolio, error = function(error) NULL)
  if (!is.list(maps)) return(NULL)
  sort(vapply(maps, function(row) paste(row$portfolio_id, row$status), character(1L), USE.NAMES = FALSE))
}
