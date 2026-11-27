# Published observations -> explicit private draft -> review -> separate completion.
new_data_market_valuation_service_v1 <- function(project_root, context, cli_runner = NULL) {
  if (!isTRUE(runtime_context_valid(context)) || !identical(context$runtime_mode, "desktop_product") ||
      !identical(context$role, "desktop_owner")) stop("desktop_market_valuation_context_invalid", call. = FALSE)
  cli <- file.path(project_root, "scripts", "desktop_market_valuation.py")
  python <- Sys.which("python3"); slot <- NULL; saved <- list()
  if (!file.exists(cli) || !nzchar(python)) stop("desktop_market_valuation_input_invalid", call. = FALSE)
  base <- list(context = list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id),
               data_space_path=runtime_data_space_path(context))
  run <- function(command, payload) {
    value <- c(base,list(payload=payload))
    if (!is.null(cli_runner)) result <- cli_runner(command,value) else {
      mask <- Sys.umask("0077"); errors <- tempfile("valuation-stderr-")
      on.exit({Sys.umask(mask);unlink(errors)},add=TRUE)
      text <- suppressWarnings(system2(python,c("-B","-E","-s",shQuote(cli),command),stdout=TRUE,stderr=errors,
        input=as.character(jsonlite::toJSON(value,auto_unbox=TRUE,null="null",digits=NA))))
      result <- tryCatch(if(length(text)==1L)jsonlite::fromJSON(text,simplifyVector=FALSE)else NULL,error=function(e)NULL)
      if (file.exists(errors) && length(readLines(errors,warn=FALSE))) result <- NULL
      if (!is.null(attr(text,"status")) && attr(text,"status")!=0L && identical(result$status,"completed")) result <- NULL
    }
    if (!is.list(result) || !identical(result$status,"completed")) {
      code <- if(is.list(result))result$code else NULL
      if(!is.character(code)||length(code)!=1L||!grepl("^desktop_market_valuation_[a-z_]+$",code))code<-"desktop_market_valuation_input_invalid"
      stop(code,call.=FALSE)
    }
    result$value
  }
  list(prepare=function(request){slot<<-NULL;value<-run("prepare",request);slot<<-value;value},
       invalidate=function(){slot<<-NULL;invisible(NULL)},
       detail=function(ordinal){if(is.null(slot))stop("desktop_market_valuation_input_invalid",call.=FALSE);run("detail",list(preview_ref=slot$preview_ref,ordinal=as.integer(ordinal)))},
       complete=function(review,confirmed){
         if(!isTRUE(confirmed)||is.null(slot)||!isTRUE(slot$valuation_draft_write)||!identical(review,slot))stop("desktop_market_valuation_confirmation_required",call.=FALSE)
         if(identical(slot$source_policy,"staged_review_only"))stop("desktop_market_valuation_staged_not_published",call.=FALSE)
         ref<-slot$preview_ref;slot<<-NULL
         grant<-run("confirm",list(preview_ref=ref,confirmed=TRUE))$confirmation
         value<-run("publish",list(confirmation=grant))
         if(!is.list(value)||!isTRUE(value$valuation_publication)||!identical(value$valuation_draft_write,FALSE)||!identical(value$preview_ref,ref))stop("desktop_market_valuation_input_invalid",call.=FALSE)
         value},
       run_binding=function(ref,as_of_date)run("portfolio-input",list(preview_ref=ref,as_of_date=as_of_date)),
       read_completed=function(){value<-run("list",list(read_only=TRUE));saved<<-value$completed;value},
       open_completed=function(ref){
         matches<-Filter(function(value)identical(value$preview_ref,ref),saved)
         if(length(matches)!=1L)stop("desktop_market_valuation_input_invalid",call.=FALSE)
         slot<<-matches[[1L]];slot})
}

data_market_valuation_ui_v1 <- function() shiny::tagList(
  shiny::tags$h3("Tagesbewertung prüfen und abschließen"),
  shiny::p('EUR-Kurse bleiben EUR. Nur andere Kurswährungen benötigen FX. Forttragung erzeugt sichtbar gekennzeichnete Ersatzwerte, keine Originalkurse und keine Feiertagsbelege.'),
  shiny::checkboxInput('valuation_expert','Expertenmodus · eigene Kalender und Sonderfälle',FALSE),
  shiny::conditionalPanel("output.valuation_trade_available == 'true'", shiny::checkboxInput('valuation_trade_prices','Bei manueller Methode: bestätigte Trade-Kurse dieses Assets als Preisreferenz verwenden; Stück-/Kontrakteinheit geprüft',FALSE)),
  shiny::p("Originalkurse bleiben erhalten. Dieser Schritt erstellt einen privaten Bewertungsentwurf, ruft keinen Kursanbieter ab und verändert keine versiegelten Zwischenstände. Zeitraum und EUR-Ziel gelten aus der Abdeckung oben. Ein Ergebnis mit Lücken ist kein Portfolioabschluss."),
  shiny::radioButtons("valuation_scope","Umfang",c("Oben ausgewähltes Asset"="current","Eigene Auswahl"="selection","Alle bewertbaren Assets"="all"),selected='current',inline=TRUE),
  shiny::conditionalPanel("input.valuation_scope == 'selection'",
    shiny::selectizeInput("valuation_assets","Assets aus der Liste auswählen",choices=NULL,multiple=TRUE,
      options=list(create=FALSE,openOnFocus=TRUE,placeholder="Liste öffnen oder Assetnamen suchen",plugins=list("remove_button"))),
    shiny::p("Nur vorhandene Assets auswählen; freie Texte sind keine Auswahl."),
    shiny::textOutput("valuation_asset_selection_status")),
  shiny::conditionalPanel('input.valuation_expert',
  shiny::checkboxInput("valuation_saved_calendars","Gespeicherte, kontextgebundene Kalender für Notierungen und FX verwenden",FALSE),
  shiny::p("Gespeicherte Profile benötigen eine passende Zuordnung und Gültigkeit. Nicht mit Regelvorschlägen oder zusätzlichen Schließtagen kombinieren; fehlende Profile bleiben ausdrücklich offen."),
  shiny::checkboxInput("valuation_rules","Offline-Regelkalender für NYSE/Nasdaq und Xetra vorschlagen (2000–2030; vor Abschluss prüfen)",FALSE),
  shiny::p("Regelvorschläge sind keine live überprüften Börsenmeldungen. Andere Notierungen erhalten keine Feiertagsannahmen. FX nutzt ausschließlich seinen eigenen Kalender. Echte Beobachtungen haben Vorrang."),
  shiny::numericInput("valuation_max_age","Höchstalter bei belegten Schließtagen (Kalendertage)",5,min=0,max=366,step=1)),
  shiny::tags$fieldset(shiny::tags$legend('Bewertungsregeln · getrennt vom Kursdatenabruf'),
    shiny::radioButtons('valuation_gap_mode','Tage ohne nativen Kurs (Quelllücken, handelsfreie Tage der Quelle)',
      c('Letzten gültigen Kurs übertragen · jeder so gefüllte Tag wird als abgeleitet gekennzeichnet'='last_valid',
        'Strikt · Tage bleiben offen, Gesamtwert bleibt unvollständig'='strict'),selected='last_valid'),
    shiny::conditionalPanel("input.valuation_gap_mode == 'last_valid'",
      shiny::numericInput('valuation_gap_max_age','Höchstalter des übertragenen Kurses (Kalendertage; leer = ohne Grenze)',value=NA,min=1,max=366,step=1)),
    shiny::p('Nur bereits gespeicherte Quelllücken sind ersetzbar, nicht offene Abrufe oder technische Sperren. Originalkurse und Quelllücken bleiben unverändert. Ersatzwerte werden ausschließlich für die Bewertung abgeleitet; kein Abruf beim Kursanbieter, keine Datenreparatur. Fehlende gehaltene Positionen dürfen nicht still aus einer Gesamtsumme verschwinden.')),
  shiny::conditionalPanel('input.valuation_expert',
  shiny::tags$details(shiny::tags$summary("Zusätzliche belegte Schließtage – getrennt nach Börse und FX-Paar"),
    shiny::textAreaInput("valuation_market_exceptions","Börse;Datum;Begründung (eine Zeile je Tag, ohne Kopfzeile)",value=""),
    shiny::textAreaInput("valuation_fx_exceptions","Ausgangswährung/EUR;Datum;Begründung (keine Aktienfeiertage übernehmen)",value="")),
  shiny::checkboxInput("valuation_include_staged","Vorgemerkte Ergebnisse des geladenen Sammelabrufs nur für diese Bewertungsvorschau einbeziehen",FALSE)),
  shiny::actionButton("valuation_prepare","Kalender-/EUR-Bewertungsentwurf erstellen"),
  shiny::uiOutput("valuation_status"),shiny::tableOutput("valuation_stage_dispositions"),shiny::tableOutput("valuation_summary"),
  shiny::selectInput("valuation_detail_asset","Tageswerte und Kalender prüfen",choices=NULL),
  shiny::conditionalPanel('input.valuation_expert',shiny::tableOutput("valuation_calendar")),
  shiny::selectInput('valuation_day_filter','Tageswerte anzeigen',c('Offene Tage'='open','Fortgetragene / ersatzbewertete Tage'='imputed','Alle Tage'='all'),selected='open'),
  shiny::tableOutput("valuation_days"),
  shiny::tags$details(shiny::tags$summary("Kalenderbewusster Bedarf an Kursen und FX – nur Planung, kein ausführbarer Sammelabruf"),
    shiny::p("Reine Schließtagsspannen benötigen keinen Abruf, sind aber keine Kursabdeckung. Quelllücken benötigen eine eigene Prüfung. Technische Sperren und bestehende Sammelabrufe werden nicht umgangen. Abrufe und Veröffentlichungen separat bestätigen."),
    shiny::tableOutput("valuation_requirements"),shiny::tableOutput("valuation_fetch_ranges"),shiny::tableOutput("valuation_requirement_days")),

  shiny::conditionalPanel("input.valuation_expert && input.valuation_saved_calendars",shiny::actionButton("valuation_prepare_batch","Kalenderbedarf als nativen Sammelabruf vorbereiten")),
  # Bestaetigen und Abschliessen erscheinen nur zu einem lebenden Entwurf. Jede
  # Aenderung an Auswahl, Umfang oder Optionen verwirft ihn; vorher fuehrte ein
  # Klick hier nur zu einem rohen Fehlercode (#189-Nachlauf, 20.09.2026).
  shiny::uiOutput("valuation_confirm_block"),
  shiny::uiOutput("valuation_completion_result"),
  shiny::actionButton("valuation_read_completed","Abgeschlossene Bewertungen lesen"),
  shiny::tableOutput("valuation_completed"),
  shiny::selectInput("valuation_saved_ref","Abgeschlossene Bewertung",choices=NULL),
  shiny::actionButton("valuation_open_completed","Gespeicherte Tageswerte ohne Berechnung öffnen")
)

data_market_valuation_policy_v1 <- function(mode, age) {
  if(is.null(mode))mode<-'last_valid'
  if(identical(mode,'strict'))return(list(mode='strict',max_age_days=NULL,age_unit='calendar_days'))
  if(!identical(mode,'last_valid'))stop('desktop_market_valuation_policy_invalid',call.=FALSE)
  # Leeres Feld heisst ausdruecklich ohne Altersgrenze (#283): eine duenne oder
  # haendisch gepflegte Kursreihe darf beliebig grosse Luecken fortschreiben.
  if(length(age)!=1L||is.na(age))return(list(mode='last_valid',max_age_days=NULL,age_unit='calendar_days'))
  if(!is.numeric(age)||!is.finite(age)||age<1||age>366||age!=as.integer(age))stop('desktop_market_valuation_policy_invalid',call.=FALSE)
  list(mode='last_valid',max_age_days=as.integer(age),age_unit='calendar_days')
}
data_market_valuation_policy_label_v1 <- function(policy) {
  if(is.null(policy)||identical(policy$mode,'strict'))return('Strikt · keine Ersatzkurse für unerklärte Quelllücken')
  paste('Letzter gültiger Kurs · höchstens',policy$max_age_days,'Kalendertage · Kurs und benötigtes FX getrennt geprüft')
}
# Abgeleitete Tage in einem Satz: uebertragene Kurse sind keine nativen Kurse (#283).
data_market_valuation_derived_label_v1 <- function(rows) {
  if (!length(rows)) return("keine abgeleiteten Tage")
  count <- function(key) sum(vapply(rows, function(row) if (is.null(row[[key]])) 0L else as.integer(row[[key]]), integer(1L)))
  derived <- count("market_imputed_day_count") + count("fx_imputed_day_count") +
    count("market_substituted_day_count") + count("fx_substituted_day_count")
  if (!derived) return("keine abgeleiteten Tage")
  sprintf("%d Tage mit übertragenem Kurs (abgeleitet, nicht nativ)", derived)
}

data_market_valuation_quality_label_v1 <- function(value) {
  if(is.null(value))return('nicht ausgewiesen (älterer Abschluss)')
  switch(value,complete='vollständig im Bewertungsumfang',substituted='ersatzwertgestützt',incomplete='unvollständig', 'unvollständig')
}

data_market_valuation_exceptions_v1 <- function(text) {
  output <- structure(list(),names=character())
  if(is.null(text)||!nzchar(trimws(text)))return(output)
  lines<-strsplit(text,"\n",fixed=TRUE)[[1L]]
  if(length(lines)>10000L)stop("desktop_market_valuation_input_invalid",call.=FALSE)
  for(line in lines){
    parts<-trimws(strsplit(line,";",fixed=TRUE)[[1L]])
    if(length(parts)!=3L||any(!nzchar(parts))||!grepl("^[A-Za-z0-9_/-]+$",parts[[1L]]))stop("desktop_market_valuation_input_invalid",call.=FALSE)
    key<-parts[[1L]];output[[key]]<-c(output[[key]],list(list(date=parts[[2L]],reason=parts[[3L]])))
  }
  output
}

data_market_valuation_table_v1 <- function(rows,columns) {
  if(!length(rows))return(data.frame())
  result<-lapply(columns,function(key)vapply(rows,function(row){value<-row[[key]];if(is.null(value))""else as.character(value)},character(1L)))
  names(result)<-columns;as.data.frame(result,stringsAsFactors=FALSE,check.names=FALSE)
}

data_market_valuation_server_v1 <- function(input,output,session,service,inventory,resolve_targets,notice,batch_ref=function()NULL,prepare_batch=NULL,on_invalidate=function(){},selected_asset=function()NULL) {
  review<-shiny::reactiveVal(NULL);detail<-shiny::reactiveVal(NULL);completed<-shiny::reactiveVal(NULL);acknowledged<-shiny::reactiveVal(NULL)
  last_completion<-shiny::reactiveVal(NULL)
  trade_authority<-shiny::reactiveVal(NULL)
  trade_scope<-function()list(scope=input$valuation_scope,refs=if(identical(input$valuation_scope,'current'))selected_asset()else if(identical(input$valuation_scope,'selection'))sort(input$valuation_assets)else vapply(inventory()$rows,`[[`,character(1),'asset_ref'))
  output$valuation_trade_available<-shiny::renderText({
    refs<-trade_scope()$refs
    if(any(vapply(inventory()$rows,function(row)row$asset_ref%in%refs&&identical(row$status,'manual'),logical(1))))'true'else'false'
  })
  shiny::outputOptions(output,'valuation_trade_available',suspendWhenHidden=FALSE)
  shiny::observeEvent(input$valuation_trade_prices,{
    trade_authority(if(isTRUE(input$valuation_trade_prices))trade_scope()else NULL)
  },ignoreInit=TRUE)
  shiny::observeEvent(selected_asset(),{
    trade_authority(NULL);shiny::updateCheckboxInput(session,'valuation_trade_prices',value=FALSE)
  },ignoreInit=TRUE)
  invalidate<-function(){service$invalidate();on_invalidate();acknowledged(NULL);review(NULL);detail(NULL);shiny::updateCheckboxInput(session,"valuation_confirm",value=FALSE)}
  # Fehlercodes des Kerns in Klartext; unbekannte Codes bleiben sichtbar.
  explain<-function(code){
    text<-c(
      desktop_market_valuation_confirmation_required="Der Bewertungsentwurf war nicht mehr aktuell oder nicht bestätigt. Bitte den Entwurf neu erstellen, danach nichts mehr ändern, das Häkchen setzen und abschließen.",
      desktop_market_valuation_selection_invalid="Für den gewählten Umfang liegt keine eindeutige Assetauswahl vor. Bitte Asset oder Arbeitsliste prüfen.",
      desktop_market_valuation_input_invalid="Eine Eingabe passt nicht (etwa Zeitraum oder Höchstalter). Bitte die Felder prüfen.",
      desktop_market_valuation_staged_not_published="Der Entwurf stützt sich auf vorgemerkte Quellen. Diese müssen zuerst separat veröffentlicht werden.",
      desktop_market_valuation_mapping_invalid="Die Kurszuordnung des Assets passt nicht zum Entwurf. Bitte die Kurszuordnung prüfen.")
    # Der Code bleibt sichtbar: er ist die Brücke zwischen Meldung und Protokoll.
    if (!is.character(code) || length(code) != 1L || !code %in% names(text)) code else paste0(unname(text[[code]]), " (Code: ", code, ")")
  }
  safe<-function(expr){tryCatch(force(expr),error=function(e){invalidate();notice(list(tone="warning",title="Bewertung blockiert oder Ergebnis unbestätigt",copy=explain(conditionMessage(e))))})}
  # The constant renderUI workspace is mounted lazily. Acknowledge its first
  # input binding once; later scope toggles must not resend an old selection.
  mounted<-shiny::reactiveVal(FALSE)
  shiny::observeEvent(input$valuation_scope,{
    if(input$valuation_scope %in% c("all","selection","current"))mounted(TRUE)
  })
  shiny::observe({
    shiny::req(mounted())
    rows<-inventory()$rows;refs<-vapply(rows,`[[`,character(1L),"asset_ref");labels<-vapply(rows,`[[`,character(1L),"asset_name")
    shiny::updateSelectizeInput(session,"valuation_assets",choices=stats::setNames(refs,labels),selected=intersect(shiny::isolate(input$valuation_assets),refs),server=FALSE)})
  output$valuation_asset_selection_status<-shiny::renderText({
    count<-length(inventory()$rows)
    if(!count)return("Noch keine Assetliste geladen. Bitte oben „Stammdaten neu lesen“.")
    paste(count,"Assets verfügbar ·",length(input$valuation_assets),"ausgewählt")
  })
  # Der Browser-Ref des Assets ist positionsabhaengig und wechselt bei einem
  # Katalogdurchlauf, auch wenn dasselbe Asset gewaehlt bleibt. Verglichen wird
  # deshalb der Name aus der Assetliste: Ein Durchlauf verwirft keinen Entwurf
  # mehr, ein echter Assetwechsel weiterhin (#283, 22.09.2026).
  selected_key<-function(){
    ref<-tryCatch(selected_asset(),error=function(error)"")
    if(!is.character(ref)||length(ref)!=1L)return("")
    rows<-tryCatch(inventory()$rows,error=function(error)list())
    hit<-Filter(function(row)identical(row$asset_ref,ref),rows)
    if(length(hit)==1L&&is.character(hit[[1L]]$asset_name))as.character(hit[[1L]]$asset_name)else as.character(ref)
  }
  shiny::observeEvent(list(selected_key(),input$valuation_expert,input$valuation_trade_prices,batch_ref(),input$valuation_include_staged,input$valuation_scope,input$valuation_assets,input$valuation_rules,input$valuation_saved_calendars,input$valuation_max_age,
    input$valuation_gap_mode,input$valuation_gap_max_age,input$valuation_market_exceptions,input$valuation_fx_exceptions),invalidate(),ignoreInit=TRUE)
  # Die Assetliste wird im Hintergrund neu gelesen, etwa beim Tabwechsel. Dabei
  # entsteht ein neues Listenobjekt, auch wenn dieselben Assets darin stehen -- und
  # das verwarf einen fertigen Entwurf, sobald das Neulesen spaet eintraf. Verglichen
  # wird deshalb der Inhalt, nicht das Objekt (#283, 22.09.2026).
  inventory_key<-function(){
    rows<-tryCatch(inventory()$rows,error=function(e)list())
    paste(vapply(rows,function(row)paste0(row$asset_ref,"|",row$asset_name,"|",row$status),character(1L)),collapse=";")
  }
  inventory_seen<-shiny::reactiveVal(NULL)
  shiny::observeEvent(inventory(),{
    current<-inventory_key();known<-inventory_seen();inventory_seen(current)
    if(!is.null(known)&&!identical(known,current))invalidate()
  },ignoreInit=FALSE)
  # Der Bewertungszeitraum setzt die Abdeckungsfelder mit. Deren Echo traegt oft
  # unveraenderte Werte und traf frueher erst nach einem fertigen Entwurf ein --
  # der Entwurf verschwand dann kommentarlos. Verworfen wird nur bei einem
  # tatsaechlich anderen Fenster (#283, 21.09.2026).
  coverage_window<-shiny::reactiveVal(NULL)
  shiny::observeEvent(list(input$asset_center_coverage_start,input$asset_center_coverage_end),{
    current<-c(as.character(input$asset_center_coverage_start),as.character(input$asset_center_coverage_end))
    known<-coverage_window();coverage_window(current)
    if(!is.null(known)&&!identical(known,current))invalidate()
  },ignoreInit=FALSE)
  shiny::observeEvent(input$valuation_prepare,safe({
    invalidate();rows<-inventory()$rows
    simple <- !isTRUE(input$valuation_expert)
    if(identical(input$valuation_scope,'current')) {
      rows <- Filter(function(row)identical(row$asset_ref,selected_asset()),rows)
      if(length(rows)!=1L)stop('desktop_market_valuation_selection_invalid',call.=FALSE)
    }
    if(identical(input$valuation_scope,"selection")){
      refs<-vapply(rows,`[[`,character(1L),"asset_ref");selected<-input$valuation_assets
      if(!is.character(selected)||!length(selected)||anyDuplicated(selected)||!all(selected%in%refs))stop("desktop_market_valuation_selection_invalid",call.=FALSE)
      rows<-Filter(function(row)row$asset_ref%in%selected,rows)
    }
    if(length(input$valuation_max_age)!=1L||!is.finite(input$valuation_max_age)||input$valuation_max_age!=as.integer(input$valuation_max_age))stop("desktop_market_valuation_input_invalid",call.=FALSE)
    execution_ref<-if(!simple&&isTRUE(input$valuation_include_staged))batch_ref()else NULL
    if(!simple&&isTRUE(input$valuation_include_staged)&&is.null(execution_ref))stop("desktop_market_valuation_input_invalid",call.=FALSE)
    request<-list(targets=resolve_targets(rows),execution_ref=execution_ref,start_date=as.character(input$asset_center_coverage_start),end_date=as.character(input$asset_center_coverage_end),
      valuation_policy=data_market_valuation_policy_v1(input$valuation_gap_mode,input$valuation_gap_max_age),
      target_currency="EUR",use_rules=!simple&&isTRUE(input$valuation_rules),use_saved_calendars=!simple&&isTRUE(input$valuation_saved_calendars),
      # Das Hoechstalter fuer belegte Schliesstage braucht immer eine Zahl. Bleibt das
      # Feld leer ("ohne Grenze"), gilt hier die zulaessige Obergrenze (#283).
      max_age_days=local({
        age<-if(simple&&identical(input$valuation_gap_mode,'last_valid'))input$valuation_gap_max_age else input$valuation_max_age
        if(length(age)!=1L||is.na(age))366L else as.integer(age)
      }),
      market_exceptions=data_market_valuation_exceptions_v1(if(simple)''else input$valuation_market_exceptions),fx_exceptions=data_market_valuation_exceptions_v1(if(simple)''else input$valuation_fx_exceptions))
    if(simple)request$simple_absence_policy<-TRUE
    if(isTRUE(input$valuation_trade_prices)) {
      if(!identical(trade_authority(),trade_scope()))stop('desktop_market_valuation_confirmation_required',call.=FALSE)
      request$use_trade_prices<-TRUE
    }
    value<-service$prepare(request);review(value)
    shiny::updateSelectInput(session,"valuation_detail_asset",choices=stats::setNames(vapply(value$rows,function(r)as.character(r$ordinal),character(1L)),vapply(value$rows,`[[`,character(1L),"asset_name")),selected="1")
    detail(service$detail(1L))
  }))
  shiny::observeEvent(input$valuation_prepare_batch,safe({
    v<-review()
    if(is.null(v)||!isTRUE(v$valuation_draft_write)||!isTRUE(input$valuation_expert)||!isTRUE(input$valuation_saved_calendars)||!is.function(prepare_batch))stop("desktop_market_valuation_confirmation_required",call.=FALSE)
    value<-prepare_batch(v$preview_ref)
    notice(list(tone="warning",title="Kalendergebundene native Batchvorschau",copy=paste(value$item_count,"Abrufbereiche · Vorschau unter „Bei Problemen“ → „Optionale Sammelabrufe“ prüfen und separat bestätigen · noch kein Abruf.")))
  }))
  shiny::observeEvent(input$valuation_detail_asset,safe({if(!is.null(review())&&nzchar(input$valuation_detail_asset))detail(service$detail(as.integer(input$valuation_detail_asset)))}))
  shiny::observeEvent(input$valuation_confirm,{
    acknowledged(if(isTRUE(input$valuation_confirm)&&!is.null(review()))review()$preview_ref else NULL)
  },ignoreInit=TRUE)
  shiny::observeEvent(input$valuation_complete,safe({
    if(is.null(acknowledged())||is.null(review())||!identical(acknowledged(),review()$preview_ref))stop("desktop_market_valuation_confirmation_required",call.=FALSE)
    value<-service$complete(review(),input$valuation_confirm);invalidate();last_completion(value)
    notice(list(tone=if(identical(value$valuation_status,"complete"))"positive"else"warning",title="Bewertungsergebnis gespeichert",copy=paste("Bewertung:",data_market_valuation_quality_label_v1(value$valuation_status),"·",data_market_valuation_policy_label_v1(value$valuation_policy),"· Originalkurse unverändert · kein Abruf beim Kursanbieter · kein Portfolio- oder FIFO-Abschluss")))}))
  shiny::observeEvent(input$valuation_read_completed,safe({
    values<-service$read_completed()$completed;completed(values)
    shiny::updateSelectInput(session,"valuation_saved_ref",choices=stats::setNames(vapply(values,`[[`,character(1L),"preview_ref"),vapply(values,function(v)paste(v$start_date,v$end_date,v$status,v$freshness,data_market_valuation_quality_label_v1(v$valuation_status),data_market_valuation_policy_label_v1(v$valuation_policy)),character(1L))))
  }))
  shiny::observeEvent(input$valuation_open_completed,safe({
    invalidate();value<-service$open_completed(input$valuation_saved_ref);review(value)
    shiny::updateSelectInput(session,"valuation_detail_asset",choices=stats::setNames(vapply(value$rows,function(r)as.character(r$ordinal),character(1L)),vapply(value$rows,`[[`,character(1L),"asset_name")),selected="1")
    detail(service$detail(1L))
  }))
  output$valuation_confirm_block<-shiny::renderUI({
    v<-review()
    if(is.null(v)||!isTRUE(v$valuation_draft_write))
      return(shiny::p(id="valuation_confirm_absent",class="pl-field-hint","Kein aktueller Bewertungsentwurf. Zuerst „Kalender-/EUR-Bewertungsentwurf erstellen“; danach Auswahl, Umfang und Optionen unverändert lassen — jede Änderung verwirft den Entwurf."))
    shiny::tagList(
      shiny::checkboxInput("valuation_confirm","Genau dieses Ergebnis einschließlich Bewertungsregel, Höchstalter, Ersatzwerten, Kalendern, FX-Route und sichtbaren Lücken bestätigen",FALSE),
      shiny::actionButton("valuation_complete","Bestätigte Bewertung ohne neuen Abruf abschließen"))
  })
  output$valuation_status<-shiny::renderUI({v<-review();if(is.null(v))return(shiny::p("Noch kein aktueller Bewertungsentwurf."));shiny::p(paste(v$start_date,"bis",v$end_date,"· Status:",v$status,"·",if(is.null(v$freshness))"Entwurf"else v$freshness,"·",length(v$rows),"Assets ·",v$fx_pair_count,"FX-Paare einmalig verwendet ·",data_market_valuation_derived_label_v1(v$rows),"·",v$source_policy,"· Bewertung:",data_market_valuation_quality_label_v1(v$valuation_status),"·",data_market_valuation_policy_label_v1(v$valuation_policy),"· keine stillen Auslassungen.",if(identical(v$source_policy,"staged_review_only"))"Gestagte Quellen müssen zuerst separat veröffentlicht werden."else"Nur veröffentlichte Quellen · kein Portfolioabschluss."))})
  output$valuation_completion_result<-shiny::renderUI({
    v<-last_completion();if(is.null(v))return(NULL)
    shiny::tagList(shiny::tags$h4("Bewertungsergebnis gespeichert · kein Portfolioabschluss"),
      shiny::p(v$start_date," bis ",v$end_date," · ",data_market_valuation_quality_label_v1(v$valuation_status)," · ",data_market_valuation_policy_label_v1(v$valuation_policy)),
      shiny::p("Gespeicherte Referenz: ",shiny::tags$code(v$preview_ref)),
      shiny::p("Dieser Speichernachweis ist kein aktueller Frischecheck. Dafür ‚Abgeschlossene Bewertungen lesen‘ verwenden. Native Kurscoverage und EUR-Bewertung bleiben getrennt."))
  })
  output$valuation_stage_dispositions<-shiny::renderTable(data_market_valuation_table_v1(review()$stage_dispositions,c("ordinal","kind","status","disposition")))
  output$valuation_summary<-shiny::renderTable(data_market_valuation_table_v1(review()$rows,c("asset_name","disposition","calendar","calendar_warning","day_count","valued_day_count","unavailable_day_count","market_imputed_day_count","fx_imputed_day_count","market_substituted_day_count","fx_substituted_day_count","substituted_day_count","valuation_status")))
  output$valuation_calendar<-shiny::renderTable({v<-detail();if(is.null(v))return(data.frame());rows<-list()
    for(kind in c("calendar","fx_calendar")){cal<-v[[kind]];p<-cal$profile;if(is.null(p))next;rows<-c(rows,
      list(list(kind=kind,date=paste(p$valid_from,p$valid_to),reason=paste(cal$preset,"·",p$market_code,"·",p$timezone_name,"· Profilversion",p$profile_version,"· Bindungsrevision",cal$binding_revision,"·",p$source_kind,"·",p$source_ref))),
      lapply(p$closure_dates,function(r)c(list(kind=kind),r)),lapply(p$special_open_dates,function(day)list(kind=kind,date=day,reason="special_open")))}
    data_market_valuation_table_v1(rows,c("kind","date","reason"))})
  output$valuation_days<-shiny::renderTable({
    rows<-detail()$rows
    if(identical(input$valuation_day_filter,'open'))rows<-Filter(function(r)!r$status%in%c('native','converted'),rows)
    if(identical(input$valuation_day_filter,'imputed'))rows<-Filter(function(r)isTRUE(r$substitution_used)||r$price_basis%in%c('imputed_closed_day','imputed_source_gap','imputed_after_source_gap')||r$fx_basis%in%c('imputed_closed_day','imputed_source_gap','imputed_after_source_gap'),rows)
    data_market_valuation_table_v1(rows,c("date","native_currency","original_price","effective_price","price_basis","price_source_date","price_age_days","fx_rate","fx_basis","fx_source_date","fx_age_days","direction","target_decimal","target_numerator","target_denominator","status","substitution_used","valuation_status","price_source_kind","price_native_status","fx_native_status"))})
  output$valuation_requirements<-shiny::renderTable(data_market_valuation_table_v1(review()$requirements,c("kind","consumer","disposition","calendar","unassessed_day_count","range_count","fetch_session_day_count","closed_no_fetch_day_count","source_gap_review_day_count","blocked_day_count")))
  requirement_rows<-function(field){v<-detail();rows<-list();for(kind in c("market_requirements","fx_requirements"))rows<-c(rows,lapply(v[[kind]][[field]],function(row)c(list(kind=kind),row)));rows}
  output$valuation_fetch_ranges<-shiny::renderTable(data_market_valuation_table_v1(requirement_rows("ranges"),c("kind","start_date","end_date","calendar_day_count","session_day_count")))
  output$valuation_requirement_days<-shiny::renderTable(data_market_valuation_table_v1(requirement_rows("rows"),c("kind","date","source_status","session_expected","calendar_reason","disposition","block_reason")))
  output$valuation_completed<-shiny::renderTable({rows<-lapply(completed(),function(v){v$Bewertungsregel<-data_market_valuation_policy_label_v1(v$valuation_policy);v$Bewertung<-data_market_valuation_quality_label_v1(v$valuation_status);v});data_market_valuation_table_v1(rows,c("preview_ref","start_date","end_date","status","freshness","source_policy","Bewertung","Bewertungsregel"))})
  # Wer den Zeitraum automatisch nachtraegt, muss wissen, ob gerade ein Entwurf
  # offen ist: eine spaete Aenderung wuerde ihn kommentarlos verwerfen.
  list(invalidate=invalidate,has_draft=function()!is.null(review()))
}
