# Pflegestand je Asset und Verwahrkonto, nur lesend (#423, Schritt 1).
#
# Beantwortet "bis wann sind die Transaktionen dieses Assets auf diesem Konto
# abgeglichen". Das Datum der letzten Buchung beantwortet das nicht: Viele
# Assets haben monatelang keine Buchung,
# und daran ist nicht zu erkennen, ob nichts passiert ist oder ob niemand
# nachgesehen hat.
#
# Zwei Spuren je Paar: reward pflegt der Importer, trade der Eigentuemer. Wirksam
# ist das Minimum - Rewards bis September machen die Kaeufe nicht abgeglichen.

data_asset_maintenance_error_codes_v1 <- function() c(
  "data_asset_maintenance_state_invalid", "data_asset_maintenance_context_invalid",
  "data_asset_maintenance_input_invalid", "data_asset_maintenance_adapter_failed",
  "data_asset_maintenance_preview_required", "data_asset_maintenance_confirmation_required"
)

.data_asset_maintenance_abort <- function(code) {
  if(!is.character(code)||length(code)!=1L||is.na(code)||!code%in%data_asset_maintenance_error_codes_v1()) stop("unregistered_data_asset_maintenance_error",call.=FALSE)
  stop(structure(list(message=code,call=NULL,code=code),class=c("spot_data_asset_maintenance_error","error","condition")))
}

new_data_asset_maintenance_center_v1 <- function(adapter) {
  if(!is.list(adapter)||!all(vapply(c("read","preview","apply","runs"),function(name)is.function(adapter[[name]]),logical(1L))))
    .data_asset_maintenance_abort("data_asset_maintenance_state_invalid")
  # Die Vorschau liegt im Center, nicht im Browser: Angewendet wird genau der
  # Abdruck, der zuvor gezeigt wurde, und genau einmal (#423).
  structure(list(adapter=adapter,vorschau=new.env(parent=emptyenv())),class="spot_data_asset_maintenance_center_v1")
}

data_asset_maintenance_read_v1 <- function(center, context, as_of_date) {
  if(!inherits(center,"spot_data_asset_maintenance_center_v1")) .data_asset_maintenance_abort("data_asset_maintenance_state_invalid")
  if(!isTRUE(tryCatch(runtime_context_valid(context),error=function(error)FALSE))||!identical(context$role,"desktop_owner")) .data_asset_maintenance_abort("data_asset_maintenance_context_invalid")
  datum <- if(inherits(as_of_date,"Date")) format(as_of_date,"%Y-%m-%d") else as_of_date
  if(!is.character(datum)||length(datum)!=1L||is.na(datum)||!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$",datum)) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  value <- tryCatch(center$adapter$read(context,datum),
    spot_desktop_product_adapter_domain_error=function(error)stop(error),
    error=function(error){if(inherits(error,"spot_data_asset_maintenance_error"))stop(error);.data_asset_maintenance_abort("data_asset_maintenance_adapter_failed")})
  if(!is.list(value)||!identical(as.integer(value$asset_maintenance_state_version),1L)||!identical(value$status,"available")||!is.list(value$pairs)) .data_asset_maintenance_abort("data_asset_maintenance_adapter_failed")
  if(!identical(value$canonical_write,FALSE)||!identical(value$provider_access,FALSE)||!identical(value$network_access,FALSE)) .data_asset_maintenance_abort("data_asset_maintenance_adapter_failed")
  value
}

.data_asset_maintenance_kurz <- function(value) {
  if(!is.character(value)||length(value)!=1L||is.na(value)) return("?")
  strsplit(value," ",fixed=TRUE)[[1L]][[1L]]
}

.data_asset_maintenance_datum <- function(value) {
  if(is.null(value)||!is.character(value)||length(value)!=1L||is.na(value)) return("—")
  formatted <- tryCatch(format(as.Date(value),"%d.%m.%Y"),error=function(error)NA_character_)
  if(is.na(formatted)) value else formatted
}

# Eine Zeile je Paar, aelteste Pflege zuerst. Die Spuren stehen getrennt, weil
# genau ihre Differenz die Auskunft ist: Rewards aktuell, Trades alt.
data_asset_maintenance_frame_v1 <- function(value, limit = 200L) {
  if(!is.list(value)||!is.list(value$pairs)) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  rows <- value$pairs
  if(!length(rows)) return(data.frame(Hinweis="Keine Asset-Konto-Paare mit Buchungen.",stringsAsFactors=FALSE))
  if(length(rows)>limit) rows <- rows[seq_len(limit)]
  # „abgeleitet" ist bewusst anders benannt als „geprüft bis": ohne Erklärung gilt
  # die jüngste Buchung, und das ist die schwächere Aussage (#423).
  zustand <- c(not_maintained="nicht gepflegt", complete_through="geprüft bis",
    source_maintained="Quelle pflegt bis", implied_by_last_event="abgeleitet bis",
    not_applicable="kommt nicht vor")
  spur <- function(row,name){
    s <- row$tracks[[name]]
    if(is.null(s)) return("—")
    if(identical(s$state,"not_applicable")) return("kommt nicht vor")
    if(identical(s$state,"not_maintained")) return("nicht gepflegt")
    sprintf("%s %s",unname(zustand[[s$state]]),.data_asset_maintenance_datum(s$through_date))
  }
  data.frame(
    Asset=vapply(rows,function(row).data_asset_maintenance_kurz(row$asset_label),character(1L)),
    Konto=vapply(rows,function(row).data_asset_maintenance_kurz(row$account_label),character(1L)),
    `Gepflegt bis`=vapply(rows,function(row)if(identical(row$effective_state,"not_maintained"))"nicht gepflegt" else .data_asset_maintenance_datum(row$effective_through_date),character(1L)),
    Herkunft=vapply(rows,function(row)switch(row$effective_state,complete_through="geprüft",implied_by_last_event="abgeleitet",not_maintained="—",row$effective_state),character(1L)),
    `Letzte Buchung`=vapply(rows,function(row).data_asset_maintenance_datum(row$last_event_date),character(1L)),
    Buchungen=vapply(rows,function(row)as.integer(row$event_count),integer(1L)),
    Rewards=vapply(rows,function(row)spur(row,"reward"),character(1L)),
    `Übrige Transaktionen`=vapply(rows,function(row)spur(row,"trade"),character(1L)),
    Befund=vapply(rows,function(row)
      if(isTRUE(row$declaration_outdated))"Erklärung überholt"
      else if(isTRUE(row$tracks_diverge))"Spuren laufen auseinander" else "",character(1L)),
    check.names=FALSE,stringsAsFactors=FALSE)
}

# Die Kennzahl, um die es geht: wie alt ist der schwaechste Pflegestand.
data_asset_maintenance_summary_v1 <- function(value) {
  if(!is.list(value)) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  paare <- as.integer(value$pair_count); offen <- as.integer(value$not_maintained_count)
  ueberholt <- as.integer(value$outdated_declaration_count)
  erklaert <- as.integer(value$declared_count); abgeleitet <- as.integer(value$implied_count)
  teile <- c(sprintf("%d Asset-Konto-Paare",paare))
  if(!is.na(erklaert)&&erklaert>0L) teile <- c(teile,sprintf("%d geprüft erklärt",erklaert))
  if(!is.na(abgeleitet)&&abgeleitet>0L) teile <- c(teile,sprintf("%d aus der jüngsten Buchung abgeleitet",abgeleitet))
  if(offen>0L) teile <- c(teile,sprintf("%d ohne Stand",offen))
  if(!is.null(value$oldest_through_date)) teile <- c(teile,sprintf("ältester Stand %s",.data_asset_maintenance_datum(value$oldest_through_date)))
  if(!is.null(value$newest_through_date)) teile <- c(teile,sprintf("jüngster %s",.data_asset_maintenance_datum(value$newest_through_date)))
  if(!is.na(ueberholt)&&ueberholt>0L) teile <- c(teile,sprintf("%d Erklärung%s überholt",ueberholt,if(ueberholt==1L)"" else "en"))
  auseinander <- as.integer(value$diverging_track_count)
  if(!is.na(auseinander)&&auseinander>0L) teile <- c(teile,sprintf("%d mit auseinanderlaufenden Spuren",auseinander))
  list(
    tone=if(offen>0L||(!is.na(ueberholt)&&ueberholt>0L))"warning" else "neutral",
    title=if(!is.na(erklaert)&&erklaert==0L)"Pflegestand bisher nur abgeleitet" else "Pflegestand je Asset und Konto",
    copy=paste(teile,collapse=" · "))
}

.data_asset_maintenance_center <- function(center) {
  if(!inherits(center,"spot_data_asset_maintenance_center_v1")) .data_asset_maintenance_abort("data_asset_maintenance_state_invalid")
  center
}

.data_asset_maintenance_context <- function(context) {
  if(!isTRUE(tryCatch(runtime_context_valid(context),error=function(error)FALSE))||!identical(context$role,"desktop_owner"))
    .data_asset_maintenance_abort("data_asset_maintenance_context_invalid")
  context
}

.data_asset_maintenance_iso <- function(value) {
  datum <- if(inherits(value,"Date")) format(value,"%Y-%m-%d") else value
  if(!is.character(datum)||length(datum)!=1L||is.na(datum)||!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$",datum))
    .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  datum
}

# Der Auftrag einer Pflegeerklaerung. `scope="unmoved"` ist die Sammelsetzung:
# alle Paare ohne Bewegung seit ihrem letzten Stand. `scope="selected"` nennt die
# Paare ausdruecklich.
data_asset_maintenance_request_v1 <- function(scope, through_date = NULL, pair_refs = character(),
                                              state = "complete_through") {
  if(!is.character(scope)||length(scope)!=1L||!scope%in%c("selected","unmoved")) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  if(!is.character(state)||length(state)!=1L||!state%in%c("complete_through","not_maintained")) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  refs <- if(is.null(pair_refs)) character() else as.character(pair_refs)
  refs <- refs[nzchar(refs)]
  if(anyDuplicated(refs)) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  list(track="trade", state=state,
       through_date=if(identical(state,"not_maintained")) NULL else .data_asset_maintenance_iso(through_date),
       scope=scope, pair_refs=as.list(refs))
}

data_asset_maintenance_preview_v1 <- function(center, context, request, as_of_date) {
  center <- .data_asset_maintenance_center(center); .data_asset_maintenance_context(context)
  if(!is.list(request)||!identical(sort(names(request)),sort(c("track","state","through_date","scope","pair_refs"))))
    .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  datum <- .data_asset_maintenance_iso(as_of_date)
  value <- tryCatch(center$adapter$preview(context,request,datum),
    spot_desktop_product_adapter_domain_error=function(error)stop(error),
    error=function(error){if(inherits(error,"spot_data_asset_maintenance_error"))stop(error);.data_asset_maintenance_abort("data_asset_maintenance_adapter_failed")})
  if(!is.list(value)||!identical(as.integer(value$asset_maintenance_declaration_preview_version),1L)||
     !is.character(value$preview_fingerprint)||!identical(nchar(value$preview_fingerprint),64L)||
     !identical(value$canonical_write,FALSE)) .data_asset_maintenance_abort("data_asset_maintenance_adapter_failed")
  # Nur der zuletzt gezeigte Abdruck ist anwendbar. Ein neuer Auftrag entwertet
  # die vorherige Bestaetigung, ohne dass die Oberflaeche daran denken muss.
  assign("aktuell", list(request=request, as_of_date=datum,
    preview_fingerprint=value$preview_fingerprint, confirmed=FALSE,
    context_fingerprint=runtime_context_fingerprint(context)), envir=center$vorschau)
  value
}

data_asset_maintenance_confirm_v1 <- function(center, context, preview_fingerprint) {
  center <- .data_asset_maintenance_center(center); .data_asset_maintenance_context(context)
  eintrag <- tryCatch(get("aktuell",envir=center$vorschau,inherits=FALSE),error=function(error)NULL)
  if(is.null(eintrag)||!identical(eintrag$preview_fingerprint,preview_fingerprint)||
     !identical(eintrag$context_fingerprint,runtime_context_fingerprint(context)))
    .data_asset_maintenance_abort("data_asset_maintenance_preview_required")
  eintrag$confirmed <- TRUE
  assign("aktuell", eintrag, envir=center$vorschau)
  list(status="confirmed", preview_fingerprint=preview_fingerprint, one_use=TRUE)
}

data_asset_maintenance_apply_v1 <- function(center, context, preview_fingerprint, declared_at_utc) {
  center <- .data_asset_maintenance_center(center); .data_asset_maintenance_context(context)
  eintrag <- tryCatch(get("aktuell",envir=center$vorschau,inherits=FALSE),error=function(error)NULL)
  if(is.null(eintrag)||!identical(eintrag$preview_fingerprint,preview_fingerprint)||
     !identical(eintrag$context_fingerprint,runtime_context_fingerprint(context)))
    .data_asset_maintenance_abort("data_asset_maintenance_preview_required")
  if(!isTRUE(eintrag$confirmed)) .data_asset_maintenance_abort("data_asset_maintenance_confirmation_required")
  if(!is.character(declared_at_utc)||length(declared_at_utc)!=1L||is.na(declared_at_utc)||
     !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",declared_at_utc))
    .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  # Die Bestaetigung ist nach dem Versuch verbraucht - auch wenn der Versuch
  # scheitert. Ein zweiter Klick darf keinen zweiten Vorgang starten.
  rm(list="aktuell", envir=center$vorschau)
  value <- tryCatch(center$adapter$apply(context,eintrag$request,eintrag$as_of_date,preview_fingerprint,declared_at_utc),
    spot_desktop_product_adapter_domain_error=function(error)stop(error),
    error=function(error){if(inherits(error,"spot_data_asset_maintenance_error"))stop(error);.data_asset_maintenance_abort("data_asset_maintenance_adapter_failed")})
  if(!is.list(value)||!value$status%in%c("declared","already_applied")||!identical(value$canonical_write,FALSE))
    .data_asset_maintenance_abort("data_asset_maintenance_adapter_failed")
  value
}

data_asset_maintenance_runs_v1 <- function(center, context) {
  center <- .data_asset_maintenance_center(center); .data_asset_maintenance_context(context)
  value <- tryCatch(center$adapter$runs(context),
    spot_desktop_product_adapter_domain_error=function(error)stop(error),
    error=function(error){if(inherits(error,"spot_data_asset_maintenance_error"))stop(error);.data_asset_maintenance_abort("data_asset_maintenance_adapter_failed")})
  if(!is.list(value)||!identical(as.integer(value$asset_maintenance_runs_version),1L)||!is.list(value$runs)||
     !identical(value$canonical_write,FALSE)) .data_asset_maintenance_abort("data_asset_maintenance_adapter_failed")
  value
}

# Was die Erklaerung aendern wuerde, in Worten. Ausgenommene Paare werden
# namentlich genannt - sonst erklaerte das Haekchen etwas, das nicht geprueft
# wurde (#423).
data_asset_maintenance_preview_summary_v1 <- function(preview) {
  if(!is.list(preview)) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  gruende <- c(movement_since_previous_state="Bewegung seit ihrem letzten Stand",
    no_previous_state="noch ohne Pflegestand", already_current="bereits auf diesem Stand",
    track_not_applicable="keine eigenen Transaktionen", unknown_pair="nicht mehr auffindbar")
  n <- as.integer(preview$included_count)
  teile <- character()
  if(identical(preview$state,"not_maintained")) {
    titel <- sprintf("%d Zusicherung%s zurücknehmen", n, if(identical(n,1L))"" else "en")
  } else {
    titel <- sprintf("Stichtag %s für %d Asset-Konto-Paar%s erklären",
      .data_asset_maintenance_datum(preview$through_date), n, if(identical(n,1L))"" else "e")
  }
  bewegt <- as.integer(preview$movement_since_previous_state_count)
  if(!is.na(bewegt)&&bewegt>0L) teile <- c(teile,
    sprintf("%d davon mit Bewegung seit ihrem letzten Stand", bewegt))
  ausgenommen <- if(is.null(preview$excluded)) list() else preview$excluded
  if(length(ausgenommen)) {
    nach_grund <- split(ausgenommen, vapply(ausgenommen,function(row)as.character(row$reason),character(1L)))
    for(grund in names(nach_grund)) {
      rows <- nach_grund[[grund]]
      namen <- vapply(rows,function(row)paste0(
        .data_asset_maintenance_kurz(if(is.null(row$asset_label))"?" else row$asset_label),"/",
        .data_asset_maintenance_kurz(if(is.null(row$account_label))"?" else row$account_label)),character(1L))
      gezeigt <- if(length(namen)>6L) c(namen[seq_len(6L)],sprintf("und %d weitere",length(namen)-6L)) else namen
      teile <- c(teile, sprintf("nicht mitgenommen (%s): %s",
        if(grund%in%names(gruende)) unname(gruende[[grund]]) else grund,
        paste(gezeigt,collapse=", ")))
    }
  }
  if(!length(teile)) teile <- "Keine Ausnahmen."
  list(tone=if(identical(as.integer(preview$included_count),0L))"warning" else "neutral",
       title=titel, copy=paste(teile,collapse=" · "))
}

# Die Pflegelaeufe als Tabelle: wann wurde was erklaert, aus welchem Anlass.
data_asset_maintenance_runs_frame_v1 <- function(value, limit = 50L) {
  if(!is.list(value)||!is.list(value$runs)) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  rows <- value$runs
  if(!length(rows)) return(data.frame(Hinweis="Noch kein Pflegelauf erklärt.",stringsAsFactors=FALSE))
  if(length(rows)>limit) rows <- rows[seq_len(limit)]
  umfang <- c(selected="ausgewählte Paare", unmoved="alle ohne Bewegung")
  data.frame(
    Erklärt=vapply(rows,function(row)sub("T"," ",sub("Z$","",as.character(row$declared_at_utc))),character(1L)),
    Stichtag=vapply(rows,function(row)if(is.null(row$through_date))"zurückgenommen" else .data_asset_maintenance_datum(row$through_date),character(1L)),
    Umfang=vapply(rows,function(row)if(as.character(row$scope)%in%names(umfang))unname(umfang[[as.character(row$scope)]])else as.character(row$scope),character(1L)),
    Paare=vapply(rows,function(row)length(row$pairs),integer(1L)),
    Herkunft=vapply(rows,function(row)if(identical(row$origin,"owner_manual"))"von Hand" else as.character(row$origin),character(1L)),
    check.names=FALSE,stringsAsFactors=FALSE)
}

# --- Pruefstempel am Asset-Stand (#423) -----------------------------------
#
# Derselbe Pflegestand, an der Stelle gesetzt, an der gebucht wird. Der
# Unter "Aktueller Asset-Stand" steht der Bestand, und dort laesst sich nach dem
# Einpflegen ein Pruefstempel setzen, ohne in den Abschluss zu wechseln. Kein zweiter Schreibweg: Der Stempel ist eine
# Erklaerung fuer ausdruecklich gewaehlte Paare und geht durch dieselbe Vorschau
# und denselben Abdruck.

# Die Paare eines Assets. Der Pflegestand kennt Namen, keine Refs der Oberflaeche;
# tragen mehrere Assets denselben Namen, wird nichts angeboten statt geraten.
data_asset_maintenance_stamp_model_v1 <- function(value, asset_label, same_name_count = 1L, account_label = NULL) {
  aus <- function(status) list(status=status, asset_label=NULL, pairs=list(), choices=character(), selected=character())
  if(is.null(value)||!is.list(value)||identical(value$status,"error")||!is.list(value$pairs)) return(aus("unread"))
  if(!is.character(asset_label)||length(asset_label)!=1L||is.na(asset_label)||!nzchar(asset_label)) return(aus("no_asset"))
  if(!is.numeric(same_name_count)||length(same_name_count)!=1L||is.na(same_name_count)) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  if(same_name_count>1L) { model <- aus("ambiguous"); model$asset_label <- asset_label; return(model) }
  pairs <- Filter(function(row) identical(row$asset_label, asset_label), value$pairs)
  if(!length(pairs)) { model <- aus("empty"); model$asset_label <- asset_label; return(model) }
  konten <- vapply(pairs, function(row) as.character(row$account_label), character(1L))
  pairs <- pairs[order(konten)]; konten <- sort(konten)
  namen <- konten
  doppelt <- namen %in% namen[duplicated(namen)]
  portfolio <- vapply(pairs, function(row) if(is.null(row$portfolio_label)) "" else as.character(row$portfolio_label), character(1L))
  namen[doppelt & nzchar(portfolio)] <- paste(namen[doppelt & nzchar(portfolio)], "·", portfolio[doppelt & nzchar(portfolio)])
  for(name in unique(namen[duplicated(namen)])) {
    stellen <- which(namen==name)
    namen[stellen] <- paste(name, "· Auswahl", seq_along(stellen), "von", length(stellen))
  }
  refs <- vapply(pairs, function(row) as.character(row$pair_ref), character(1L))
  # Vorbelegt wird nur, was eindeutig ist: das einzige Konto, sonst das Konto der
  # Maske. Ein Stempel fuer ein Konto, das niemand angesehen hat, waere eine
  # Zusicherung ohne Pruefung.
  vorbelegt <- if(length(refs)==1L) refs else {
    passend <- if(is.character(account_label)&&length(account_label)==1L&&!is.na(account_label)) refs[konten==account_label] else character()
    if(length(passend)==1L) passend else character()
  }
  list(status="ready", asset_label=asset_label, pairs=unname(pairs),
       choices=stats::setNames(refs, namen), selected=vorbelegt)
}

data_asset_maintenance_stamp_text_v1 <- function(model) {
  if(!is.list(model)||!is.character(model$status)||length(model$status)!=1L) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  switch(model$status,
    unread=list(tone="neutral", title="Pflegestand noch nicht gelesen",
      copy="Er wird mit dem Reiter gelesen. Bleibt das aus: unter „1. Transaktionen“ → „Bestand prüfen und Pflegestand je Asset und Konto“ den Pflegestand lesen."),
    no_asset=list(tone="neutral", title="Kein Asset gewählt",
      copy="Oben in der Suche ein Asset wählen."),
    ambiguous=list(tone="warning", title="Der Name dieses Assets ist nicht eindeutig",
      copy=paste0("Mehrere Assets heißen „", model$asset_label, "“. Der Pflegestand lässt sich hier nicht sicher zuordnen; unter „1. Transaktionen“ → „Bestand prüfen und Pflegestand je Asset und Konto“ steht jedes Paar einzeln zur Wahl.")),
    empty=list(tone="neutral", title="Noch kein Pflegestand",
      copy=paste0("Für „", model$asset_label, "“ gibt es noch keine Buchung. Ein Pflegestand entsteht mit der ersten.")),
    ready=NULL,
    .data_asset_maintenance_abort("data_asset_maintenance_input_invalid"))
}

# Die Paare des Assets als Tabelle - dieselben Spalten wie im Abschluss, ohne das
# Asset selbst.
data_asset_maintenance_stamp_frame_v1 <- function(model) {
  if(!is.list(model)||!identical(model$status,"ready")) return(NULL)
  frame <- data_asset_maintenance_frame_v1(list(pairs=model$pairs))
  frame$Konto <- names(model$choices)
  frame[, setdiff(names(frame), "Asset"), drop=FALSE]
}

# Was der Stempel aendern wuerde. `model` liefert die juengste Buchung je Paar:
# Liegt sie nach dem Stichtag, gilt der Stempel sofort als ueberholt - das soll
# vor dem Setzen dastehen, nicht danach in der Liste.
data_asset_maintenance_stamp_preview_text_v1 <- function(preview, model) {
  if(!is.list(preview)||!is.list(model)) .data_asset_maintenance_abort("data_asset_maintenance_input_invalid")
  n <- as.integer(preview$included_count)
  if(is.na(n)||n==0L) return(list(tone="warning", title="Nichts zu stempeln",
    copy="Keines der gewählten Konten lässt sich zuordnen. Pflegestand neu lesen und erneut wählen."))
  stichtag <- preview$through_date
  name <- function(ref) { treffer <- names(model$choices)[model$choices==ref]; if(length(treffer)==1L) treffer else "?" }
  zeilen <- vapply(preview$included, function(row) {
    teile <- c(sprintf("%s: bisher %s", name(row$pair_ref),
      if(is.null(row$previous_through_date)) "ohne Stand" else paste("bis", .data_asset_maintenance_datum(row$previous_through_date))))
    paar <- Filter(function(item) identical(item$pair_ref, row$pair_ref), model$pairs)
    letzte <- if(length(paar)==1L) paar[[1L]]$last_event_date else NULL
    if(is.character(letzte)&&length(letzte)==1L&&!is.na(letzte)&&letzte>stichtag) teile <- c(teile,
      sprintf("eine Buchung vom %s liegt nach dem Stichtag, der Stempel gilt damit sofort als überholt", .data_asset_maintenance_datum(letzte)))
    paste(teile, collapse=" – ")
  }, character(1L))
  nicht <- if(is.null(preview$excluded)) 0L else length(preview$excluded)
  list(tone=if(any(grepl("überholt", zeilen, fixed=TRUE))||nicht>0L) "warning" else "neutral",
    title=sprintf("Prüfstempel bis %s für %d %s", .data_asset_maintenance_datum(stichtag), n, if(n==1L) "Konto" else "Konten"),
    copy=paste(c(zeilen,
      if(nicht==1L) "1 gewähltes Konto ist nicht mehr auffindbar und bleibt außen vor"
      else if(nicht>1L) sprintf("%d gewählte Konten sind nicht mehr auffindbar und bleiben außen vor", nicht),
      "Noch nichts geschrieben; „Stempel setzen“ erklärt genau das."), collapse=" · "))
}
