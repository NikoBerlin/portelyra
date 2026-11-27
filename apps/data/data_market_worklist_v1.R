# Stable private asset identities persist; browser refs and grants never persist.
# `provider`: der Anbieter, bei dem der Vorschlag gefunden wurde (rc.394) - ein EODHD-Symbol gehoert zu EODHD, nicht zu Yahoo.
data_market_defaults_v1 <- function(asset = NULL, candidate = NULL, mapping = NULL, provider = "yahoo") {
  text <- function(x) if (is.character(x) && length(x) == 1L && !is.na(x)) x else ""
  known <- !is.null(mapping)
  currency <- if (known) text(mapping$provider_currency) else text(candidate$quote_currency)
  currency_known <- grepl("^[A-Z]{3}$", currency) && !currency %in% c('GBX','ZAC','ILA','USX')
  provider <- if (nzchar(text(provider))) text(provider) else "yahoo"
  suggestion <- data_market_currency_suggestion_v1(provider, text(candidate$symbol), text(asset$price_currency))
  # Known but unsupported quote units must never silently become major currency.
  if(nzchar(currency) && !currency_known) suggestion <- list(currency='',basis='Quotierungseinheit unklar · Nachweis des Kursanbieters prüfen; keine automatische Skalierung')
  list(provider_id = if (known) text(mapping$provider_id) else provider,
    provider_symbol = if (known) text(mapping$provider_symbol) else text(candidate$symbol),
    provider_currency = if (known) currency else if (currency_known) currency else suggestion$currency,
    exchange_code = if (known) text(mapping$exchange_code) else text(candidate$exchange),
    mic_code = if (known) text(mapping$mic_code) else "",
    currency_basis = if (known) 'Gespeicherte Zuordnung' else if (currency_known) 'Vorschlag des Kursanbieters · noch nicht verifiziert' else suggestion$basis,
    calendar = if (identical(asset$asset_type, "crypto")) "continuous_24_7" else "weekday_exchange")
}

# Yahoo suffixes identify venues, not guaranteed quote currencies. Suggestions
# have NO verification/write authority; see docs/provider-symbol-currency-research.md.
data_market_currency_suggestion_v1 <- function(provider, symbol, asset_currency = '') {
  valid <- function(x)is.character(x)&&length(x)==1L&&!is.na(x)
  result <- function(currency,basis)list(currency=currency,basis=basis,verified=FALSE)
  fallback <- if(valid(asset_currency)&&grepl('^[A-Z]{3}$',asset_currency)&&!asset_currency %in% c('GBX','ZAC','ILA','USX'))asset_currency else ''
  if(!identical(provider,'yahoo')||!valid(symbol)||!nzchar(trimws(symbol)))return(result(fallback,'Stammdatenpreiswährung · unbestätigter Formularvorschlag'))
  symbol<-toupper(trimws(symbol))
  if(grepl('(^\\^|=|[0-9]{6}[CP][0-9]{8}$)',symbol))return(result('','Index, Derivat oder FX-Symbol · Kurswährung und Einheit ausdrücklich prüfen'))
  suffix<-if(grepl('[.]',symbol))sub('^.*[.]','',symbol)else ''
  if(suffix %in% c('L','IL','AQ','XC','JO','TA'))return(result('','Mehrwährungs-/Untereinheiten-Risiko · keine GBP/GBp-, ZAR/ZAc- oder ILS-Skalierung aus dem Ticker'))
  euro<-c('DE','BE','BM','DU','F','HM','HA','MU','SG','VI','BR','HE','PA','IR','MI','TI','AS','LS','MC','AT','TL','RG','VS')
  currencies<-c(stats::setNames(rep('EUR',length(euro)),euro),SW='CHF',TO='CAD',V='CAD',CN='CAD',NE='CAD',AX='AUD',XA='AUD',NZ='NZD',T='JPY',HK='HKD',SS='CNY',SZ='CNY',ST='SEK',CO='DKK',OL='NOK',IC='ISK',NS='INR',BO='INR',KS='KRW',KQ='KRW',TW='TWD',TWO='TWD',SI='SGD',SA='BRL',MX='MXN',WA='PLN')
  if(suffix %in% names(currencies))return(result(unname(currencies[[suffix]]),paste0('Yahoo .',suffix,' · typische Handelsplatzwährung, unbestätigter Vorschlag (Ausnahmen möglich)')))
  quote<-sub('^.*-','',symbol)
  if(grepl('^[A-Z0-9]+-[A-Z]{3}$',symbol)&&quote %in% c('USD','EUR','GBP','CHF','CAD','AUD','JPY'))return(result(quote,'Yahoo Paar-Endung · Quote-Währung als unbestätigter Vorschlag'))
  if(grepl('^[A-Z]{1,6}(-[A-Z])?$',symbol))return(result('USD','Yahoo ohne Handelsplatzsuffix · USD nur als unbestätigter Vorschlag'))
  result(fallback,'Ticker nicht eindeutig · Stammdatenpreiswährung als unbestätigter Vorschlag')
}

data_market_mapping_choices_v1 <- function(rows) c('Neue Zuordnung'='',stats::setNames(
  vapply(rows,`[[`,character(1L),'ref'),vapply(rows,function(r)paste(r$capability,r$provider_id,r$provider_symbol,r$provider_currency,r$verification_status,if(isTRUE(r$enabled))'aktiv'else 'inaktiv',sep=' · '),character(1L))))

new_data_market_worklist_service_v1 <- function(project_root, context, cli_runner = NULL, domain = "provider") {
  if (!isTRUE(runtime_context_valid(context)) || !identical(context$runtime_mode, "desktop_product") ||
      !identical(context$role, "desktop_owner")) stop("desktop_market_worklist_invalid", call. = FALSE)
  cli <- file.path(normalizePath(project_root, mustWork = TRUE), "scripts", "desktop_market_worklist.py")
  if (!identical(domain, "provider")) stop("desktop_market_worklist_invalid", call. = FALSE)
  base <- list(domain = domain, context = list(tenant_id = context$tenant_id, user_id = context$user_id,
    data_space_id = context$data_space_id), data_space_path = runtime_data_space_path(context))
  current <- NULL
  run <- function(command, payload) {
    request <- c(base, list(payload = payload))
    if (!is.null(cli_runner)) result <- cli_runner(command, request) else {
      old <- Sys.umask("0077"); err <- tempfile("market-worklist-")
      on.exit({Sys.umask(old); unlink(err)}, add = TRUE)
      output <- tryCatch(suppressWarnings(system2(Sys.which("python3"), c("-B", "-E", "-s", shQuote(cli), command),
        input = as.character(jsonlite::toJSON(request, auto_unbox = TRUE, null = "null", digits = NA)),
        stdout = TRUE, stderr = err)), error = function(e) character())
      result <- tryCatch(if (length(output) == 1L) jsonlite::fromJSON(output, simplifyVector = FALSE) else NULL,
        error = function(e) NULL)
      if ((file.exists(err) && file.info(err)$size > 0) || !is.null(attr(output, "status"))) result <- NULL
    }
    if (!is.list(result) || !identical(result$status, "completed"))
      stop("desktop_market_worklist_invalid", call. = FALSE)
    current <<- result$worklist
    current
  }
  list(read = function() run("read", list(read_only = TRUE)),
    # Ohne vorher gelesene Revision blockierte das Starten, sobald eine
    # gespeicherte Arbeitsliste existierte — mit einer Meldung, die den Grund
    # nicht nannte. Starten liest sie deshalb selbst zuerst; ersetzt wird nie
    # etwas, "start" ergaenzt nur (#283, 21.09.2026).
    start = function(ids) { if (is.null(current)) run("read", list(read_only = TRUE))
      run("start", list(asset_ids = as.list(ids), expected_revision = current$revision)) },
    select = function(id) run("select", list(asset_id = id, expected_revision = current$revision)),
    update = function(id, status, draft, advance = FALSE) run("update", list(asset_id = id,
      status = status, draft = draft, advance = isTRUE(advance), expected_revision = current$revision)),
    state = function() current)
}

data_market_worklist_ui_v1 <- function(prefix = "market_worklist") {
  id <- function(suffix) paste0(prefix, "_", suffix)
  shiny::tagList(
  shiny::tags$h3("Fehlende Kurszuordnungen listenweise bearbeiten"),
  shiny::p("Nur die Arbeitsliste wird lokal gespeichert. Suche, Kurszuordnung, Testabruf und Historie bleiben separat bestätigt. Übersprungene und zurückgestellte Assets bleiben sichtbar."),
  shiny::p("Für ein einzelnes Asset genügt die Auswahl oben. Dieses Feld wirkt erst bei ‚Arbeitsliste starten / ergänzen‘ und startet selbst keinen Abruf beim Kursanbieter."),
  shiny::selectizeInput(id("selection"), "Auswahl für die Arbeitsliste (leer: alle ohne Zuordnung für Tageskurse)", choices = NULL, multiple = TRUE),
  shiny::div(class = "pl-editor-actions",
    shiny::actionButton(id("start"), "Arbeitsliste starten / ergänzen"),
    shiny::actionButton(id("load"), "Gespeicherte Arbeitsliste fortsetzen"),
    shiny::actionButton(id("pause"), "Entwurf speichern und pausieren")),
  shiny::uiOutput(id("status")),
  shiny::div(class = "pl-table-wrap", style = "max-height:240px;overflow:auto", shiny::tableOutput(id("table"))),
  shiny::selectInput(id("item"), "Eintrag erneut öffnen", c("Zuerst Arbeitsliste laden" = "")),
  shiny::div(class = "pl-editor-actions",
    shiny::actionButton(id("open"), "Eintrag öffnen"),
    shiny::actionButton(id("back"), "Zurück"),
    shiny::actionButton(id("skip"), "Überspringen und weiter"),
    shiny::actionButton(id("defer"), "Später klären und weiter")),
  shiny::actionButton(id("reviewed"), "Vorhandene Zuordnung übernehmen und weiter"),
  shiny::p("Nach bestätigtem Speichern einer neuen Zuordnung folgt das nächste offene Asset. Testabruf und Aktivierung können weiterhin offen sein; eine gespeicherte Zuordnung ist noch keine verifizierte Historie.")
  )
}
