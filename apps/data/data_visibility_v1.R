# Einordnung der Data-App (#492). Festlegung nach der Durchsicht aller Karten am 23.10.2026:
# - Alltag: immer sichtbar.
# - Experte: nur mit dem Schalter "Expertenwerkzeuge" in den Einstellungen.
# - Nur bei Problemen: mit dem Schalter oder von selbst, sobald der Anlass vorliegt, der die Karte noetig macht.
# Geloescht wird nichts: Mit dem Schalter ist alles erreichbar wie bisher. Der Verweis "Unklarer Ausgang?" in der
# Transaktionsmaske blendet beides fuer die laufende Sitzung ein (input.data_expert_tools_reveal).
#
# Die meisten Anlaesse liest die App ohnehin. Unterbrochene CSV-Importe und Skalenanpassungen prueft sie einmal nach dem
# ersten Aufbau der Seite. Ohne eigenen Anlass bleiben
# nur Karten, die sich nicht billig erkennen lassen (gesperrte Tage, Kalender- und Quellluecken): bei Schalter und Verweis.

DATA_VISIBILITY_SIGNALS_V1 <- c(
  setup = "Die Datenablage ist noch nicht eingerichtet.",
  portfolio = "Es gibt noch kein Portfolio.",
  tax_setup = "Der Steuerbereich ist noch nicht eingerichtet.",
  tax_module = "Für eine Projektionsart ist kein gültiges Regelmodul gewählt.",
  history_halted = "„Alles aktualisieren“ wurde angehalten.",
  market_setup_failed = "Eine Kurs-Einrichtung ist abgebrochen.",
  statement_failed = "Ein Börsen-Import ist abgebrochen.",
  action_failed = "Eine Aktion hat einen Fehler gemeldet.",
  cash_recovery = "Ein Cash-Schreibversuch hat keinen eindeutigen Ausgang.",
  inherited_rates = "Fonds erben ihre Teilfreistellung vom Asset-Typ.",
  csv_resume = "Ein CSV-Import ist unterbrochen.",
  scale_resume = "Eine Skalenanpassung ist unterbrochen."
)

.data_visibility_expert_js_v1 <- "output.data_expert_tools == 'on' || input.data_expert_tools_reveal == 1"

# Wie shiny::conditionalPanel; inline als span, etwa fuer einen Knopf in der Kopfzeile (conditionalPanel kennt kein inline).
.data_visibility_panel_v1 <- function(condition, ..., inline = FALSE)
  (if (isTRUE(inline)) shiny::tags$span else shiny::tags$div)(class = "shiny-panel-conditional", `data-display-if` = condition, `data-ns-prefix` = "", ...)

data_expert_only_v1 <- function(..., inline = FALSE) .data_visibility_panel_v1(.data_visibility_expert_js_v1, ..., inline = inline)

# signal = NULL: ohne eigenen Anlass, also nur mit Schalter oder Verweis.
data_when_needed_v1 <- function(signal, ..., inline = FALSE) {
  if (is.null(signal)) return(data_expert_only_v1(..., inline = inline))
  if (!is.character(signal) || length(signal) != 1L || !signal %in% names(DATA_VISIBILITY_SIGNALS_V1))
    stop("data_visibility_signal_unknown", call. = FALSE)
  .data_visibility_panel_v1(sprintf("%s || output.data_need_%s == 'on'", .data_visibility_expert_js_v1, signal), ..., inline = inline)
}

# Nur beim Anlass, auch im Expertenmodus nicht sonst (rc.387): fuer Hinweise, die ohne Anlass falsch waeren - etwa "Noch kein
# Portfolio" (#547). data_when_needed_v1 zeigt im Expertenmodus immer; fuer Werkzeuge ist das gewollt, fuer Hinweise nicht.
data_when_signal_v1 <- function(signal, ..., inline = FALSE) {
  if (!is.character(signal) || length(signal) != 1L || !signal %in% names(DATA_VISIBILITY_SIGNALS_V1))
    stop("data_visibility_signal_unknown", call. = FALSE)
  .data_visibility_panel_v1(sprintf("output.data_need_%s == 'on'", signal), ..., inline = inline)
}

# signals: benannte Liste von Funktionen ohne Argument, die TRUE liefern, solange der Anlass besteht. Sie laufen reaktiv;
# ein Fehler beim Lesen gilt als "kein Anlass" - die Karte bleibt dann beim Schalter.
data_visibility_server_v1 <- function(output, signals) {
  unknown <- setdiff(names(signals), names(DATA_VISIBILITY_SIGNALS_V1))
  if (length(unknown)) stop("data_visibility_signal_unknown", call. = FALSE)
  for (name in names(signals)) local({
    signal <- signals[[name]]; id <- paste0("data_need_", name)
    output[[id]] <- shiny::renderText(if (isTRUE(tryCatch(signal(), error = function(error) FALSE))) "on" else "off")
    shiny::outputOptions(output, id, suspendWhenHidden = FALSE)
  })
  invisible(names(signals))
}

# Bausteine (#542, Festlegung 06.11. und 10.11.2026): Was ein abgeschalteter Baustein umfasst, bietet die Data-App nicht an. Die
# Ausgabe output$data_module_<key> ("on"/"off") setzt data_portfolio_configuration_server_v1 aus dem wirksamen Umfang des Datenraums
# (ein Baustein laeuft, sobald ein aktives Portfolio ihn nutzt). Bedingung "!= 'off'": Solange nichts gelesen ist, ohne Speicher und
# mit allen Bausteinen steht alles da wie bisher. Abschalten loescht nichts; die Vorschau des Kerns nennt, was entfaellt.
DATA_MODULES_V1 <- c("cash", "market_data", "history_analysis", "tax_report", "tax_projection", "documents")

# `also`: weitere Bedingungen, unter denen der Bereich trotzdem steht (etwa ein gewaehltes Asset, das den Baustein nutzt).
data_module_condition_v1 <- function(module, also = NULL) {
  if (!is.character(module) || length(module) != 1L || !module %in% DATA_MODULES_V1) stop("data_module_unknown", call. = FALSE)
  paste(c(sprintf("output.data_module_%s != 'off'", module), also), collapse = " || ")
}

data_module_only_v1 <- function(module, ..., inline = FALSE, also = NULL)
  .data_visibility_panel_v1(data_module_condition_v1(module, also), ..., inline = inline)

# Ganze Reiter eines tabsetPanel: Der Reiterkopf (li) traegt die Bedingung. Wird der offene Reiter ausgeblendet, springt die Auswahl
# auf den ersten sichtbaren daneben. `conditions`: benannte Liste Reiterwert -> Bedingung (data_module_condition_v1). Sichtbar heisst
# berechnet sichtbar: Shiny 1.8 setzt display:none am Element, neuere Fassungen blenden ueber eine CSS-Regel aus (#583).
data_module_tabs_v1 <- function(tabset, conditions) {
  count <- 0L
  value_of <- function(node) {
    links <- Filter(function(child) inherits(child, "shiny.tag") && identical(child$name, "a"), node$children)
    if (length(links)) links[[1L]]$attribs[["data-value"]] else NULL
  }
  walk <- function(node) {
    if (inherits(node, "shiny.tag")) {
      value <- if (identical(node$name, "li")) value_of(node) else NULL
      if (is.character(value) && length(value) == 1L && value %in% names(conditions)) {
        count <<- count + 1L
        node$attribs[["data-display-if"]] <- conditions[[value]]; node$attribs[["data-ns-prefix"]] <- ""
        node$attribs[["data-pl-module-tab"]] <- "1"
      }
      node$children <- lapply(node$children, walk)
    } else if (is.list(node) && !inherits(node, "html_dependency") && !is.function(node)) {
      node[] <- lapply(node, walk)
    }
    node
  }
  result <- walk(tabset)
  if (count != length(conditions)) stop("data_module_tab_missing", call. = FALSE)
  shiny::tagList(result, .data_module_tabs_script_v1())
}

.data_module_tabs_script_v1 <- function() shiny::tags$script(shiny::HTML(paste0(
  "if(!window.__plModuleTabs){window.__plModuleTabs=1;$(document).on('hidden','li[data-pl-module-tab]',function(e){",
  "if(e.target!==this)return;var a=this.querySelector('a');if(!this.classList.contains('active')&&!(a&&a.classList.contains('active')))return;",
  "var items=this.parentElement.children;for(var i=0;i<items.length;i++){var li=items[i];",
  "if(li!==this&&getComputedStyle(li).display!=='none'&&li.querySelector('a')){$(li.querySelector('a')).tab('show');break;}}});}")))
