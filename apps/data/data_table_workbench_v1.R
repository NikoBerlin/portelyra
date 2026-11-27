# Auswaehlbare, filterbare Tabelle - ein Baustein fuer mehrere Karten (#424).
#
# Im ganzen Projekt gab es keine auswaehlbaren Tabellenzeilen: Buchungen wurden
# ueber ein selectizeInput mit sehr vielen Eintraegen gewaehlt, waehrend die Tabelle mit
# denselben Buchungen daneben stand. Das war der Grund, warum die Bedienung sich
# umstaendlich anfuehlte.
#
# Bewusst ohne DT: das Paket steht nicht in
# den Imports von spotcore, und eine neue Laufzeitabhaengigkeit soll dafuer nicht
# entstehen. Die Auswahl laeuft ueber Shiny.setInputValue, wie an anderen Stellen
# der App auch.
#
# Der Filter ist generisch gehalten, weil weitere Tabellen ihn brauchen werden. Er kennt vier Arten von Spalten:
#
#   choice  - Auswahl aus den vorkommenden Werten (Transaktionsart, Konto)
#   date    - Zeitraum von/bis
#   number  - Betrag groesser/kleiner
#   text    - Teiltext, Gross- und Kleinschreibung ohne Belang

data_table_workbench_error_codes_v1 <- function() c(
  "data_table_workbench_input_invalid", "data_table_workbench_spec_invalid"
)

.data_table_workbench_abort <- function(code) {
  if(!is.character(code)||length(code)!=1L||is.na(code)||!code%in%data_table_workbench_error_codes_v1()) stop("unregistered_data_table_workbench_error",call.=FALSE)
  stop(structure(list(message=code,call=NULL,code=code),class=c("spot_data_table_workbench_error","error","condition")))
}

# Eine Spaltenbeschreibung: welche Spalte, welcher Filtertyp, welche Beschriftung. `format` bereitet nur die Anzeige auf
# (#529 Punkt 8: Datum TT.MM.JJJJ, Betrag mit Einheit) und bekommt die Werte der Spalte und den ganzen Datenrahmen;
# gefiltert wird weiter auf den Werten selbst.
data_table_workbench_column_v1 <- function(name, label = name, filter = "none", align = "left", format = NULL) {
  if(!is.character(name)||length(name)!=1L||is.na(name)||!nzchar(name)) .data_table_workbench_abort("data_table_workbench_spec_invalid")
  if(!filter%in%c("none","choice","date","number","text")) .data_table_workbench_abort("data_table_workbench_spec_invalid")
  if(!align%in%c("left","right")) .data_table_workbench_abort("data_table_workbench_spec_invalid")
  if(!is.null(format)&&!is.function(format)) .data_table_workbench_abort("data_table_workbench_spec_invalid")
  list(name=name,label=label,filter=filter,align=align,format=format)
}

.data_table_workbench_check <- function(frame, columns) {
  if(!is.data.frame(frame)) .data_table_workbench_abort("data_table_workbench_input_invalid")
  if(!is.list(columns)||!length(columns)) .data_table_workbench_abort("data_table_workbench_spec_invalid")
  for(column in columns) {
    if(!is.list(column)||!all(c("name","label","filter","align")%in%names(column))) .data_table_workbench_abort("data_table_workbench_spec_invalid")
    if(!column$name%in%names(frame)) .data_table_workbench_abort("data_table_workbench_spec_invalid")
  }
  invisible(TRUE)
}

# Die Filterzeile. Je Spalte mit Filter genau ein Bedienelement, benannt nach dem
# gemeinsamen Praefix - damit eine Karte mehrere Tabellen tragen kann.
data_table_workbench_filter_ui_v1 <- function(id, frame, columns) {
  .data_table_workbench_check(frame, columns)
  feld <- function(suffix) paste0(id,"_filter_",suffix)
  steuer <- list()
  for(column in columns) {
    if(identical(column$filter,"none")) next
    werte <- frame[[column$name]]
    if(identical(column$filter,"choice")) {
      vorhanden <- sort(unique(as.character(werte[!is.na(werte)&nzchar(as.character(werte))])))
      steuer[[length(steuer)+1L]] <- shiny::selectizeInput(feld(column$name), column$label,
        choices=vorhanden, multiple=TRUE, options=list(placeholder="alle"))
    } else if(identical(column$filter,"date")) {
      steuer[[length(steuer)+1L]] <- shiny::div(
        desktop_product_empty_date_input_v1(feld(paste0(column$name,"_von")), paste(column$label,"von")),
        desktop_product_empty_date_input_v1(feld(paste0(column$name,"_bis")), paste(column$label,"bis")))
    } else if(identical(column$filter,"number")) {
      steuer[[length(steuer)+1L]] <- shiny::div(
        shiny::textInput(feld(paste0(column$name,"_min")), paste(column$label,"ab"), "", placeholder="kein Mindestwert"),
        shiny::textInput(feld(paste0(column$name,"_max")), paste(column$label,"bis"), "", placeholder="kein Höchstwert"))
    } else {
      steuer[[length(steuer)+1L]] <- shiny::textInput(feld(column$name), column$label, "", placeholder="Teiltext")
    }
  }
  if(!length(steuer)) return(NULL)
  shiny::tags$details(class="pl-disclosure",
    shiny::tags$summary("Filter · Vorgabe zeigt alle Zeilen"),
    shiny::div(class="pl-form-grid", steuer),
    shiny::div(class="pl-editor-actions",
      shiny::actionButton(paste0(id,"_filter_clear"), "Filter zurücksetzen", class="btn-default")))
}

.data_table_workbench_zahl <- function(value) {
  if(is.null(value)||!is.character(value)||length(value)!=1L||is.na(value)||!nzchar(trimws(value))) return(NA_real_)
  suppressWarnings(as.numeric(sub(",",".",trimws(value),fixed=TRUE)))
}

# Die Zeilen, die nach dem Filter uebrig bleiben. Gibt Indizes zurueck, nicht den
# Datenrahmen: so bleibt die Zuordnung zur Auswahl erhalten.
data_table_workbench_rows_v1 <- function(id, frame, columns, input) {
  .data_table_workbench_check(frame, columns)
  if(!nrow(frame)) return(integer(0))
  behalten <- rep(TRUE, nrow(frame))
  lese <- function(suffix) tryCatch(input[[paste0(id,"_filter_",suffix)]], error=function(error)NULL)
  for(column in columns) {
    werte <- frame[[column$name]]
    if(identical(column$filter,"choice")) {
      gewaehlt <- lese(column$name)
      if(length(gewaehlt)) behalten <- behalten & as.character(werte)%in%as.character(gewaehlt)
    } else if(identical(column$filter,"date")) {
      als_datum <- suppressWarnings(as.Date(as.character(werte)))
      von <- lese(paste0(column$name,"_von")); bis <- lese(paste0(column$name,"_bis"))
      if(inherits(von,"Date")&&length(von)==1L&&!is.na(von)) behalten <- behalten & !is.na(als_datum) & als_datum>=von
      if(inherits(bis,"Date")&&length(bis)==1L&&!is.na(bis)) behalten <- behalten & !is.na(als_datum) & als_datum<=bis
    } else if(identical(column$filter,"number")) {
      als_zahl <- suppressWarnings(as.numeric(gsub("[^0-9.,-]","",as.character(werte))))
      als_zahl <- suppressWarnings(as.numeric(sub(",",".",as.character(als_zahl),fixed=TRUE)))
      min_wert <- .data_table_workbench_zahl(lese(paste0(column$name,"_min")))
      max_wert <- .data_table_workbench_zahl(lese(paste0(column$name,"_max")))
      if(!is.na(min_wert)) behalten <- behalten & !is.na(als_zahl) & als_zahl>=min_wert
      if(!is.na(max_wert)) behalten <- behalten & !is.na(als_zahl) & als_zahl<=max_wert
    } else if(identical(column$filter,"text")) {
      text <- lese(column$name)
      if(is.character(text)&&length(text)==1L&&!is.na(text)&&nzchar(trimws(text)))
        behalten <- behalten & grepl(trimws(text), as.character(werte), fixed=FALSE, ignore.case=TRUE)
    }
  }
  which(behalten)
}

# Die Tabelle selbst. Jede Zeile traegt ein Kaestchen; die Auswahl geht als Liste
# von Zeilenschluesseln an den Server. Ein Klick auf die Zeile schaltet das
# Kaestchen mit - sonst muesste man das kleine Feld treffen.
data_table_workbench_table_v1 <- function(id, frame, columns, keys, selected = character(),
                                          height = "26rem", single = FALSE, empty = "Keine Zeilen.") {
  .data_table_workbench_check(frame, columns)
  if(!is.character(keys)||length(keys)!=nrow(frame)||anyNA(keys)) .data_table_workbench_abort("data_table_workbench_input_invalid")
  if(!nrow(frame)) return(shiny::p(class="pl-field-hint", empty))
  art <- if(isTRUE(single)) "radio" else "checkbox"
  sammeln <- sprintf(
    "var rows=document.querySelectorAll('#%s_grid input[data-row]');var out=[];rows.forEach(function(b){if(b.checked)out.push(b.getAttribute('data-row'));});Shiny.setInputValue('%s_selected',out,{priority:'event'});",
    id, id)
  kopf <- shiny::tags$tr(
    shiny::tags$th(style="width:2.2rem"),
    lapply(columns, function(column) shiny::tags$th(column$label,
      style=if(identical(column$align,"right"))"text-align:right" else NULL)))
  # Die Zeilen als Text, nicht als Tag-Objekte: Eine Buchungsliste hat schnell
  # einige hundert Zeilen, und je Zeile neun Tags zu bauen kostete merklich Zeit - bei jedem Sitzungsstart, seit die Liste von selbst laedt. Alles, was aus Daten stammt, wird maskiert.
  merkmal <- function(value) htmltools::htmlEscape(value, attribute=TRUE)
  zeilenklick <- merkmal(sprintf("var b=this.querySelector('input[data-row]');if(event.target!==b){if(b.type==='radio'){b.checked=true;}else{b.checked=!b.checked;}}%s",sammeln))
  zellen <- do.call(paste0, lapply(columns, function(column) {
    wert <- as.character(frame[[column$name]])
    if(is.function(column$format)) wert <- as.character(column$format(wert, frame))
    sprintf('<td style="%s">%s</td>',
      if(identical(column$align,"right"))"text-align:right;white-space:nowrap" else "white-space:nowrap",
      ifelse(is.na(wert), "—", htmltools::htmlEscape(wert)))
  }))
  zeilen <- shiny::HTML(paste0(
    '<tr onclick="', zeilenklick, '" style="cursor:pointer"><td><input type="', art, '" name="', merkmal(paste0(id,"_row")),
    '" data-row="', merkmal(keys), '"', ifelse(keys %in% selected, " checked", ""), ' onclick="', merkmal(sammeln), '"/></td>',
    zellen, "</tr>", collapse="\n"))
  # Nicht "<id>_table": der uiOutput, der diese Tabelle traegt, heisst in der
  # Buchungsauswahl selbst "activity_rows_table". Beide Kennungen waren
  # identisch, und damit stand dieselbe ID zweimal im Dokument (#424).
  shiny::div(id=paste0(id,"_grid"), class="pl-table-wrap",
    style=sprintf("max-height:%s;overflow:auto",height),
    shiny::tags$table(class="table table-sm table-striped",
      shiny::tags$thead(kopf), shiny::tags$tbody(zeilen)))
}

# Was die Auswahl bedeutet - der Satz, der in der Karte steht. Er traegt die
# Entscheidung: keine Zeile heisst anlegen, eine Zeile heisst
# bearbeiten oder stornieren.
data_table_workbench_selection_hint_v1 <- function(selected, total, filtered) {
  n <- length(selected)
  zusatz <- if(filtered<total) sprintf(" · %d von %d Zeilen durch den Filter gezeigt",filtered,total) else sprintf(" · %d Zeilen",total)
  if(n==0L) list(tone="neutral", title="Keine Zeile gewählt",
      copy=paste0("Es wird eine neue Buchung angelegt. Für Bearbeiten oder Stornieren eine Zeile wählen.",zusatz))
  else if(n==1L) list(tone="warning", title="Eine Buchung gewählt",
      copy=paste0("Sie kann bearbeitet oder storniert werden.",zusatz))
  else list(tone="warning", title=sprintf("%d Buchungen gewählt",n),
      copy=paste0("Mehrere Buchungen lassen sich gemeinsam stornieren oder mit \u201eweiter\u201c einzeln durchgehen.",zusatz))
}
