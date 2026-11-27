data_asset_activity_correction_error_codes_v1 <- function() c(
  "data_asset_activity_correction_state_invalid", "data_asset_activity_correction_context_invalid",
  "data_asset_activity_correction_candidate_invalid", "data_asset_activity_correction_preview_required",
  "data_asset_activity_correction_confirmation_required", "data_asset_activity_correction_confirmation_consumed",
  "data_asset_activity_correction_confirmation_expired", "data_asset_activity_correction_adapter_failed"
)

.data_asset_activity_correction_time <- function(value) {
  as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

.data_asset_activity_correction_abort <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% data_asset_activity_correction_error_codes_v1()) stop("unregistered_data_asset_activity_correction_error", call.=FALSE)
  stop(structure(list(message=code,call=NULL,code=code),class=c("spot_data_asset_activity_correction_error","error","condition")))
}

.data_asset_activity_correction_context <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context),error=function(error)FALSE)) || !identical(context$runtime_mode,"desktop_product") || !identical(context$role,"desktop_owner")) .data_asset_activity_correction_abort("data_asset_activity_correction_context_invalid")
  context
}

new_data_asset_activity_correction_product_adapter_v1 <- function(project_root, context) {
  project_root<-normalizePath(project_root,winslash="/",mustWork=TRUE);data_space<-runtime_data_space_path(context)
  drafts<-new_data_activity_draft_product_adapter_v1(project_root,context)
  trusted<-function(bound){.data_asset_activity_correction_context(bound);if(!identical(runtime_context_fingerprint(bound),runtime_context_fingerprint(context))) .data_asset_activity_correction_abort("data_asset_activity_correction_context_invalid");list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id,actor_id=context$actor_id,role="desktop_owner")}
  run<-function(command,payload) tryCatch(.per_asset_review_adapter_run(project_root,command,payload),error=function(error){if(inherits(error,"spot_data_asset_activity_correction_error")||inherits(error,"spot_desktop_product_adapter_domain_error"))stop(error);.data_asset_activity_correction_abort("data_asset_activity_correction_adapter_failed")})
  candidates<-function(bound)run("activity-correction-candidates",list(context=trusted(bound),data_space_path=data_space))$candidates
  preview<-function(bound,predecessor,replacement,at){
    available<-candidates(bound)$candidates
    if(!is.character(predecessor)||anyNA(predecessor)||!length(predecessor)||anyDuplicated(predecessor)||
       (length(predecessor)>1L&&!is.null(replacement))) .data_asset_activity_correction_abort("data_asset_activity_correction_candidate_invalid")
    matches<-Filter(function(item)is.list(item)&&item$event_ref%in%predecessor,available)
    if(length(matches)!=length(predecessor)) .data_asset_activity_correction_abort("data_asset_activity_correction_candidate_invalid")
    action<-if(is.null(replacement))"void"else"correct"
    created<-drafts$create(bound,matches[[1L]]$portfolio_ref,"correction",action,if(is.null(replacement))list()else replacement,at,predecessor)
    validated<-drafts$validate(bound,created$trusted_draft$draft_ref,created$trusted_draft$revision,at)
    draft<-validated$trusted_draft
    if(identical(draft$validation_status,"blocked")) {
      # Der Kern hat abgelehnt. Bis rc.231 endete das hier im Sammelcode
      # data_asset_activity_correction_adapter_failed; jetzt wird der Grund
      # geholt - nur lesend - und nach oben gereicht (#420). Scheitert das
      # Erklaeren selbst, bleibt es beim bisherigen Code.
      explanation<-tryCatch(drafts$explain(bound,draft$draft_ref)[[1L]],error=function(error)NULL)
      if(is.list(explanation)&&explanation$status%in%c("explained","no_longer_blocked")) data_activity_block_reason_signal_v1(explanation)
    }
    if(!identical(draft$validation_status,"ready")||!is.list(draft$validation$domain_public_preview)) .data_asset_activity_correction_abort("data_asset_activity_correction_adapter_failed")
    list(public_preview=draft$validation$domain_public_preview,trusted_preview=draft)
  }
  confirmation<-function(bound,preview,challenge,issued,expires){
    draft_challenge<-paste0("adc_",substr(digest::digest(charToRaw(enc2utf8(paste(preview$validation$validation_fingerprint,challenge,sep="|"))),algo="sha256",serialize=FALSE),1L,32L))
    drafts$confirmation(bound,preview,draft_challenge,issued,issued,expires)
  }
  apply<-function(bound,preview,confirmation,at)drafts$apply(bound,preview$draft_ref,confirmation,at)$trusted_draft$domain_result
  list(
    candidates=candidates,preview=preview,confirmation=confirmation,apply=apply,
    history=function(bound)run("activity-correction-history",list(context=trusted(bound),data_space_path=data_space))$history
  )
}

new_data_asset_activity_correction_center_v1 <- function(adapter) {
  required<-c("candidates","preview","confirmation","apply","history")
  if(!is.list(adapter)||!identical(names(adapter),required)||!all(vapply(adapter,is.function,logical(1L)))) .data_asset_activity_correction_abort("data_asset_activity_correction_state_invalid")
  center<-new.env(hash=FALSE,parent=emptyenv());center$adapter<-adapter;center$candidates<-new.env(hash=TRUE,parent=emptyenv());center$previews<-new.env(hash=TRUE,parent=emptyenv());center$sequence<-0L;class(center)<-"spot_data_asset_activity_correction_center_v1";center
}

.data_asset_activity_correction_check <- function(center) {
  if(!inherits(center,"spot_data_asset_activity_correction_center_v1")||!is.environment(center)||!is.environment(center$candidates)||!is.environment(center$previews)) .data_asset_activity_correction_abort("data_asset_activity_correction_state_invalid")
}

# Optionaler Assetfilter: `asset_ref` ist die browserlokale Editor-Ref des
# Formularziels. Gefiltert wird serverseitig ueber die interne Asset-Identitaet
# des Kandidaten, niemals ueber Anzeigelabels - Assetnamen sind nicht eindeutig.
# Der Browser erhaelt weiterhin ausschliesslich die redigierte Public-Sicht ohne
# kanonische IDs. Kandidaten aus `keep_refs` bleiben unabhaengig vom Filter
# erhalten, damit eine bereits uebernommene Auswahl nicht unsichtbar wird.
# Registriert bleiben im Center stets alle Kandidaten; gefiltert wird nur das
# zurueckgegebene Ergebnis.
data_asset_activity_correction_refresh_v1 <- function(center, context, activity_editor=NULL, asset_ref=NULL, keep_refs=character()) {
  .data_asset_activity_correction_check(center);.data_asset_activity_correction_context(context);value<-center$adapter$candidates(context)
  if(!is.list(value)||!value$status%in%c("absent","available")||!is.list(value$candidates)) .data_asset_activity_correction_abort("data_asset_activity_correction_adapter_failed")
  rm(list=ls(center$candidates,all.names=TRUE),envir=center$candidates)
  items<-lapply(value$candidates,function(item){if(!is.list(item)||!is.character(item$candidate_ref)||!is.list(item$event)||!is.list(item$public)) .data_asset_activity_correction_abort("data_asset_activity_correction_adapter_failed");assign(item$candidate_ref,item,envir=center$candidates);item})
  scalar<-function(x)is.character(x)&&length(x)==1L&&!is.na(x)&&nzchar(x)
  if(!is.null(activity_editor)&&scalar(asset_ref)) {
    if(!is.null(keep_refs)&&!is.character(keep_refs)) .data_asset_activity_correction_abort("data_asset_activity_correction_candidate_invalid")
    # Der Filter ist Komfort, keine Schreibgrenze: Liegt noch keine zum Kontext
    # passende Editor-Auswahl vor, bleibt die Liste ungefiltert statt zu
    # scheitern. Ohne Identitaetszuordnung wird nichts geraten.
    selection<-tryCatch(.data_asset_activity_selection(activity_editor,context),error=function(error)NULL)
    if(!is.null(selection)) {
      kept<-if(is.null(keep_refs))character()else keep_refs
      items<-Filter(function(item){
        if(item$candidate_ref %in% kept) return(TRUE)
        identical(unname(selection$assets$ref_by_id[[item$event$asset_ref]]),asset_ref)
      },items)
    }
  }
  public<-lapply(items,function(item)item$public)
  list(status=value$status,candidates=public,history=center$adapter$history(context),canonical_ids_exposed=FALSE,path_exposed=FALSE)
}

# Buchungsschluessel je Kandidat, nur serverseitig: fuer Angaben, die an der
# Buchung selbst haengen (Belegangaben). Die oeffentliche Liste traegt ihn nicht.
data_asset_activity_correction_event_refs_v1 <- function(center) {
  .data_asset_activity_correction_check(center)
  refs<-ls(center$candidates,all.names=TRUE)
  stats::setNames(vapply(refs,function(ref)as.character(get(ref,envir=center$candidates,inherits=FALSE)$event_ref),character(1L)),refs)
}
# Buchungsart je Kandidat, nur serverseitig: Manche Angaben gibt es nur an einer Art (der Wert am Abgang).
data_asset_activity_correction_event_types_v1 <- function(center) {
  .data_asset_activity_correction_check(center)
  refs<-ls(center$candidates,all.names=TRUE)
  stats::setNames(vapply(refs,function(ref)as.character(get(ref,envir=center$candidates,inherits=FALSE)$event$event_type),character(1L)),refs)
}
.data_asset_activity_correction_candidate <- function(center, ref) {
  if(!is.character(ref)||length(ref)!=1L||is.na(ref)||!exists(ref,envir=center$candidates,inherits=FALSE)) .data_asset_activity_correction_abort("data_asset_activity_correction_candidate_invalid")
  get(ref,envir=center$candidates,inherits=FALSE)
}

data_asset_activity_correction_prefill_v1 <- function(center, activity_editor, context, candidate_ref) {
  .data_asset_activity_correction_check(center);candidate<-.data_asset_activity_correction_candidate(center,candidate_ref);selection<-.data_asset_activity_selection(activity_editor,context);event<-candidate$event
  mapped<-function(area,id,optional=FALSE){if(is.null(id)&&optional)return("");value<-unname(selection[[area]]$ref_by_id[[id]]);if(is.null(value)) .data_asset_activity_correction_abort("data_asset_activity_correction_candidate_invalid");value}
  list(
    event_type=event$event_type,portfolio_ref=mapped("portfolios",candidate$portfolio_ref),account_ref=mapped("accounts",event$account_ref),related_account_ref=mapped("accounts",event$related_account_ref,TRUE),
    asset_ref=mapped("assets",event$asset_ref),source_asset_ref=mapped("assets",event$source_asset_ref,TRUE),event_time_evidence=event$event_time_evidence,local_date=event$local_date,
    local_time=if(is.null(event$local_time))""else event$local_time,time_zone=event$time_zone,effective_at_utc=if(is.null(event$effective_at_utc))""else event$effective_at_utc,
    original_acquired_time_evidence=event$original_acquired_time_evidence,original_acquired_local_date=if(is.null(event$original_acquired_local_date))""else event$original_acquired_local_date,
    original_acquired_local_time=if(is.null(event$original_acquired_local_time))""else event$original_acquired_local_time,original_acquired_time_zone=if(is.null(event$original_acquired_time_zone))""else event$original_acquired_time_zone,
    original_acquired_at_utc=if(is.null(event$original_acquired_at_utc))""else event$original_acquired_at_utc,amount_input_mode=event$amount_input_mode,basis_evidence_mode=event$basis_evidence_mode,
    quantity_decimal=if(is.null(event$quantity_decimal))""else event$quantity_decimal,eligible_quantity_decimal=if(is.null(event$eligible_quantity_decimal))""else event$eligible_quantity_decimal,
    unit_price_decimal=if(is.null(event$unit_price_decimal))""else event$unit_price_decimal,gross_amount_decimal=if(is.null(event$gross_amount_decimal))""else event$gross_amount_decimal,
    monetary_fee_decimal=if(is.null(event$monetary_fee_decimal))""else event$monetary_fee_decimal,asset_fee_quantity_decimal=if(is.null(event$asset_fee_quantity_decimal))""else event$asset_fee_quantity_decimal,
    provided_basis_decimal=if(is.null(event$provided_basis_decimal))""else event$provided_basis_decimal,movement_context_code=event$movement_context_code
  )
}

data_asset_activity_correction_prepare_v1 <- function(center, activity_editor, context, candidate_ref, action_type, replacement_form, now_utc) {
  .data_asset_activity_correction_check(center);.data_asset_activity_correction_context(context)
  if(!is.character(candidate_ref)||!length(candidate_ref)||anyNA(candidate_ref)||anyDuplicated(candidate_ref)||
     (length(candidate_ref)>1L&&!identical(action_type,"void"))) .data_asset_activity_correction_abort("data_asset_activity_correction_candidate_invalid")
  candidates<-lapply(candidate_ref,function(ref).data_asset_activity_correction_candidate(center,ref))
  predecessor<-vapply(candidates,`[[`,character(1L),"event_ref")
  if (!is.character(now_utc) || length(now_utc) != 1L || is.na(.data_asset_activity_correction_time(now_utc))) {
    .data_asset_activity_correction_abort("data_asset_activity_correction_candidate_invalid")
  }
  if(!is.character(action_type)||length(action_type)!=1L||!action_type%in%c("correct","void")) .data_asset_activity_correction_abort("data_asset_activity_correction_candidate_invalid")
  replacement<-if(identical(action_type,"void"))NULL else .data_asset_activity_form(activity_editor,context,replacement_form)$events[[1L]]
  # Ein bekannter Ablehnungsgrund traegt interne Kennungen; hier werden daraus
  # Konto- und Assetbezeichnungen der Sitzung, bevor er die Oberflaeche erreicht.
  value<-tryCatch(center$adapter$preview(context,predecessor,replacement,now_utc),spot_data_activity_block_reason_signal=function(signal){
    selection<-tryCatch(.data_asset_activity_selection(activity_editor,context),error=function(error)NULL)
    label<-function(kind,internal_id){
      area<-selection[[paste0(kind,"s")]];ref<-unname(area$ref_by_id[[internal_id]])
      if(is.null(ref))NULL else area$by_ref[[ref]]$label
    }
    data_activity_block_reason_abort_v1(signal$explanation,label)
  })
  if(!is.list(value)||!is.list(value$public_preview)||!is.list(value$trusted_preview)) .data_asset_activity_correction_abort("data_asset_activity_correction_adapter_failed")
  center$sequence<-center$sequence+1L;ref<-sprintf("correction_preview_%04d",center$sequence)
  expires_at_utc <- format(.data_asset_activity_correction_time(now_utc) + 600, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  assign(ref,list(trusted=value$trusted_preview,confirmed=FALSE,consumed=FALSE,context_fingerprint=runtime_context_fingerprint(context),expires_at_utc=expires_at_utc),envir=center$previews)
  c(value$public_preview,list(preview_ref=ref, one_attempt_only=TRUE, expires_at_utc=expires_at_utc))
}

data_asset_activity_correction_confirm_v1 <- function(center, preview_ref, context = NULL) {
  .data_asset_activity_correction_check(center);if(!is.character(preview_ref)||!exists(preview_ref,envir=center$previews,inherits=FALSE)) .data_asset_activity_correction_abort("data_asset_activity_correction_preview_required")
  entry <- get(preview_ref,envir=center$previews,inherits=FALSE)
  if (!is.null(context)) {
    .data_asset_activity_correction_context(context)
    if (!identical(runtime_context_fingerprint(context), entry$context_fingerprint)) {
      .data_asset_activity_correction_abort("data_asset_activity_correction_confirmation_expired")
    }
  }
  if (isTRUE(entry$consumed)) .data_asset_activity_correction_abort("data_asset_activity_correction_confirmation_consumed")
  entry$confirmed<-TRUE
  assign(preview_ref,entry,envir=center$previews)
  list(confirmation_version=1L, preview_ref=preview_ref, status="confirmed", one_use=TRUE)
}

data_asset_activity_correction_execute_v1 <- function(center, context, preview_ref, now_utc, expires_at_utc) {
  .data_asset_activity_correction_check(center);.data_asset_activity_correction_context(context);if(!is.character(preview_ref)||!exists(preview_ref,envir=center$previews,inherits=FALSE)) .data_asset_activity_correction_abort("data_asset_activity_correction_preview_required")
  entry<-get(preview_ref,envir=center$previews,inherits=FALSE)
  if (isTRUE(entry$consumed)) .data_asset_activity_correction_abort("data_asset_activity_correction_confirmation_consumed")
  now_time <- .data_asset_activity_correction_time(now_utc)
  expires_time <- .data_asset_activity_correction_time(expires_at_utc)
  reference_expires <- .data_asset_activity_correction_time(entry$expires_at_utc)
  if (!is.character(now_utc) || length(now_utc) != 1L || is.na(now_time) ||
      !is.character(expires_at_utc) || length(expires_at_utc)!=1L || is.na(expires_time) ||
      now_time > expires_time ||
      now_time > reference_expires ||
      !identical(entry$context_fingerprint, runtime_context_fingerprint(context))) {
    .data_asset_activity_correction_abort("data_asset_activity_correction_confirmation_expired")
  }
  if(!isTRUE(entry$confirmed)) .data_asset_activity_correction_abort("data_asset_activity_correction_confirmation_required")
  entry$consumed<-TRUE
  entry$confirmed<-FALSE
  assign(preview_ref,entry,envir=center$previews)
  challenge<-paste0("aac_",substr(digest::digest(charToRaw(enc2utf8(paste(entry$trusted$plan_fingerprint,now_utc,sep="|"))),algo="sha256",serialize=FALSE),1L,32L))
  confirmation<-center$adapter$confirmation(context,entry$trusted,challenge,now_utc,entry$expires_at_utc)
  result <- center$adapter$apply(context,entry$trusted,confirmation,now_utc)
  result
}

data_asset_activity_batch_review_ui_v2 <- function(preview) {
  if(is.null(preview)||is.null(preview$selected_event_count)) return(NULL)
  exact<-function(x) {
    if(is.null(x)) return('—')
    if(is.list(x)) {
      if(!is.null(x$decimal)) return(gsub('.',',',x$decimal,fixed=TRUE))
      if(!is.null(x$numerator_integer)&&!is.null(x$denominator_integer)) return(paste(x$numerator_integer,'/',x$denominator_integer))
      return(if(identical(x$exactness_status,'basis_missing'))'Basis fehlt'else'Nicht anwendbar')
    }
    gsub('.',',',as.character(x),fixed=TRUE)
  }
  table<-function(headers,rows) shiny::div(class='pl-table-wrap',shiny::tags$table(class='table table-striped table-bordered',
    shiny::tags$thead(shiny::tags$tr(lapply(headers,shiny::tags$th))),
    shiny::tags$tbody(lapply(rows,function(row)shiny::tags$tr(lapply(row,function(cell)shiny::tags$td(cell)))))))
  types<-c(buy='Kauf',sell='Verkauf',transfer='Transfer',deposit='Zugang',withdrawal='Abgang',dividend='Dividende',stock_dividend='Stockdividende',reward='Reward')
  rows<-lapply(preview$selected_events,function(e){
    type<-unname(types[e$event_type]);if(is.na(type))type<-e$event_type
    list(e$portfolio_label,e$account_label,e$asset_label,paste(e$local_date,if(is.null(e$local_time))'ohne Uhrzeit'else e$local_time,e$time_zone),
      type,exact(e$quantity_decimal),exact(e$unit_price_decimal),exact(e$gross_amount_decimal),e$basis_currency,
      exact(e$monetary_fee_decimal),exact(e$asset_fee_quantity_decimal),if(is.null(e$related_account_label))'—'else e$related_account_label)
  })
  fields<-c(remaining_quantity_decimal='Bestand',remaining_fifo_basis='Einstandswert',cost_average='Ø Einstandskurs',realized_gross_proceeds='Realisierter Bruttoerlös',realized_fifo_basis='Einstandswert verkauft',realized_gain='Realisierter Gewinn',gross_income='Bruttoertrag',monetary_fees='Geldgebühren')
  worlds<-lapply(preview$batch_fifo_changes,function(change){
    before<-change$before;after<-change$after
    fifo<-lapply(names(fields),function(field)list(unname(fields[[field]]),exact(before[[field]]),if(is.null(after))'Keine verbleibenden Ereignisse'else exact(after[[field]])))
    custody<-function(side,label)if(is.null(side))list()else lapply(side$custody_positions,function(row)list(label,paste0(row$account_label,' · Konto ',row$account_ordinal),exact(row$remaining_quantity_decimal)))
    shiny::tags$details(open=if(length(preview$batch_fifo_changes)<=3L)'open'else NULL,
      shiny::tags$summary(paste(before$portfolio_label,'·',before$asset_label,'·',before$basis_currency,'· Bestand',exact(before$remaining_quantity_decimal),'→',if(is.null(after))'keine Ereignisse'else exact(after$remaining_quantity_decimal))),
      table(c('Portfolio × Asset','Vorher','Nachher'),fifo),
      shiny::h5('Verwahrung – getrennt von der Portfolio-/Asset-FIFO-Basis'),
      table(c('Stand','Konto','Menge'),c(custody(before,'Vorher'),custody(after,'Nachher'))))
  })
  shiny::tagList(shiny::h4(paste(preview$selected_event_count,'ausgewählte Buchungen')),
    table(c('Portfolio','Konto','Asset','Zeitpunkt','Art','Menge','Stückpreis','Bruttowert','Währung','Geldgebühr','Assetgebühr','Gegenkonto'),rows),
    shiny::h4('Gemeinsame FIFO- und Verwahrvorschau'),worlds,
    shiny::p('Genau diese Auswahl, eine neue Generation. Historische Fakten bleiben erhalten. Keine Cash-Buchung, kein Kursabruf.'))
}

new_data_realized_state_product_adapter_v2 <- function(project_root, context) {
  project_root<-normalizePath(project_root,winslash="/",mustWork=TRUE);data_space<-runtime_data_space_path(context);canonical<-runtime_canonical_path(context)
  trusted<-function(bound){.data_asset_activity_correction_context(bound);if(!identical(runtime_context_fingerprint(bound),runtime_context_fingerprint(context))) .data_asset_activity_correction_abort("data_asset_activity_correction_context_invalid");list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id,actor_id=context$actor_id,role="desktop_owner")}
  run<-function(command,payload).per_asset_review_adapter_run(project_root,command,payload)
  list(
    read=function(bound)run("realized-state-read",list(context=trusted(bound),data_space_path=data_space))$model,
    materialize=function(bound,mode,at,completeness)run("realized-state-materialize",list(context=trusted(bound),data_space_path=data_space,request_mode=mode,requested_at_utc=at,portfolio_completeness=completeness))$result,
    verify=function(bound)run("realized-state-verify",list(context=trusted(bound),data_space_path=data_space))$result,
    readiness=function(bound)run("portfolio-readiness-read",list(context=trusted(bound),canonical_path=canonical,data_space_path=data_space))$model
  )
}
