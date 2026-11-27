data_activity_draft_error_codes_v1 <- function() c(
  "data_activity_draft_state_invalid", "data_activity_draft_context_invalid",
  "data_activity_draft_handle_invalid", "data_activity_draft_input_invalid",
  "data_activity_draft_validation_required", "data_activity_draft_confirmation_required",
  "data_activity_draft_adapter_failed"
)

.data_activity_draft_abort <- function(code) {
  if(!is.character(code)||length(code)!=1L||is.na(code)||!code%in%data_activity_draft_error_codes_v1()) stop("unregistered_data_activity_draft_error",call.=FALSE)
  stop(structure(list(message=code,call=NULL,code=code),class=c("spot_data_activity_draft_error","error","condition")))
}

.data_activity_draft_context <- function(context) {
  if(!isTRUE(tryCatch(runtime_context_valid(context),error=function(error)FALSE))||!identical(context$runtime_mode,"desktop_product")||!identical(context$role,"desktop_owner")) .data_activity_draft_abort("data_activity_draft_context_invalid")
  context
}

.data_activity_draft_time <- function(value) {
  if(!is.character(value)||length(value)!=1L||is.na(value)) return(as.POSIXct(NA))
  as.POSIXct(value,format="%Y-%m-%dT%H:%M:%SZ",tz="UTC")
}

new_data_activity_draft_center_v1 <- function(adapter) {
  required<-c("resolve_time","inspect_redundant","create","create_or_reuse","update","resolve_fee","bind_fifo_order","read","validate","confirmation","apply","resume","list","profile_save","profile_list","profile_read")
  if(!is.list(adapter)||!all(required%in%names(adapter))||anyDuplicated(names(adapter))||!all(vapply(adapter,is.function,logical(1L)))) .data_activity_draft_abort("data_activity_draft_state_invalid")
  center<-new.env(hash=FALSE,parent=emptyenv());center$adapter<-adapter;center$entries<-new.env(hash=TRUE,parent=emptyenv());center$sequence<-0L;class(center)<-"spot_data_activity_draft_center_v1";center
}

.data_activity_draft_check <- function(center) {
  if(!inherits(center,"spot_data_activity_draft_center_v1")||!is.environment(center)||!is.environment(center$entries)||!is.integer(center$sequence)) .data_activity_draft_abort("data_activity_draft_state_invalid")
}

.data_activity_draft_call <- function(callback) {
  tryCatch(callback(),spot_desktop_product_adapter_domain_error=function(error)stop(error),error=function(error){if(inherits(error,"spot_data_activity_draft_error")||inherits(error,"spot_data_reward_daily_close_error"))stop(error);.data_activity_draft_abort("data_activity_draft_adapter_failed")})
}

.data_activity_draft_handle <- function(center, trusted) {
  center$sequence<-center$sequence+1L;handle<-sprintf("activity_draft_%04d",center$sequence)
  assign(handle,list(draft_ref=trusted$draft_ref,revision=as.integer(trusted$revision),trusted=trusted,confirmation=NULL),envir=center$entries);handle
}

.data_activity_draft_entry <- function(center, handle) {
  if(!is.character(handle)||length(handle)!=1L||is.na(handle)||!exists(handle,envir=center$entries,inherits=FALSE)) .data_activity_draft_abort("data_activity_draft_handle_invalid")
  get(handle,envir=center$entries,inherits=FALSE)
}

.data_activity_draft_public <- function(value, handle) {
  if(!is.list(value)||!is.list(value$public_draft)||!is.list(value$trusted_draft)) .data_activity_draft_abort("data_activity_draft_adapter_failed")
  c(value$public_draft,list(draft_handle=handle))
}

data_activity_draft_create_v1 <- function(center,context,portfolio_id,origin_type,action_type,event_fields,now_utc,predecessor_event_ref=NULL) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  if(is.na(.data_activity_draft_time(now_utc))||!origin_type%in%c("manual_form","tolerant_csv","correction")||!action_type%in%c("create","correct","void")) .data_activity_draft_abort("data_activity_draft_input_invalid")
  value<-.data_activity_draft_call(function()center$adapter$create(context,portfolio_id,origin_type,action_type,event_fields,now_utc,predecessor_event_ref))
  handle<-.data_activity_draft_handle(center,value$trusted_draft);.data_activity_draft_public(value,handle)
}

data_activity_draft_create_manual_v1 <- function(center,context,portfolio_id,event_fields,now_utc) data_activity_draft_create_v1(center,context,portfolio_id,"manual_form","create",event_fields,now_utc)
data_activity_draft_create_tolerant_csv_v1 <- function(center,context,portfolio_id,event_fields,now_utc) data_activity_draft_create_v1(center,context,portfolio_id,"tolerant_csv","create",event_fields,now_utc)

data_activity_draft_create_or_reuse_tolerant_csv_v1 <- function(center,context,portfolio_id,event_fields,source_binding,source_auxiliary,now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  if(is.na(.data_activity_draft_time(now_utc))||!is.list(source_binding)||!is.list(source_auxiliary)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  value<-.data_activity_draft_call(function()center$adapter$create_or_reuse(context,portfolio_id,event_fields,source_binding,source_auxiliary,now_utc))
  handle<-.data_activity_draft_handle(center,value$trusted_draft)
  c(.data_activity_draft_public(value,handle),list(created_new=isTRUE(value$created_new),reused_existing=isTRUE(value$reused_existing)))
}

data_activity_draft_create_correction_v1 <- function(center,context,portfolio_id,action_type,event_fields,predecessor_event_ref,now_utc) data_activity_draft_create_v1(center,context,portfolio_id,"correction",action_type,event_fields,now_utc,predecessor_event_ref)

data_activity_draft_update_v1 <- function(center,context,draft_handle,event_patch=list(),remove_fields=character(),now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(is.na(.data_activity_draft_time(now_utc))||!is.list(event_patch)||!is.character(remove_fields)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  value<-.data_activity_draft_call(function()center$adapter$update(context,entry$draft_ref,entry$revision,event_patch,remove_fields,now_utc))
  entry$revision<-as.integer(value$trusted_draft$revision);entry$trusted<-value$trusted_draft;entry$confirmation<-NULL;assign(draft_handle,entry,envir=center$entries)
  .data_activity_draft_public(value,draft_handle)
}

# Gleiche Sekunde wie eine gebuchte Buchung desselben Coins (rc.323): Der Reward rueckt um ganze Sekunden nach hinten, wie beim
# Krypto-Import seit rc.272. Ohne Zusammenstoss mit einer gebuchten Buchung bleibt er, wie er ist (shift_seconds 0).
data_activity_draft_shift_past_booked_second_v1 <- function(center,context,draft_handle,now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(is.na(.data_activity_draft_time(now_utc))||!is.function(center$adapter$shift_second)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  value<-.data_activity_draft_call(function()center$adapter$shift_second(context,entry$draft_ref,entry$revision,now_utc))
  entry$revision<-as.integer(value$draft$trusted_draft$revision);entry$trusted<-value$draft$trusted_draft;entry$confirmation<-NULL;assign(draft_handle,entry,envir=center$entries)
  list(shift_status=value$shift_status,shift_seconds=as.integer(value$shift_seconds))
}

data_activity_draft_shift_note_v1 <- function(count) if(isTRUE(count>0L)) sprintf(" · %d um ganze Sekunden versetzt – derselbe Coin hatte in dieser Sekunde schon eine gebuchte Buchung",as.integer(count)) else ""

# Ein Reward, den die Pruefung wegen "gleicher Zeitpunkt" ablehnt, wird versetzt und neu geprueft - nur, wenn der Zeitpunkt mit einer
# schon gebuchten Buchung desselben Coins zusammenfaellt (etwa ein gebuchter Reward auf dem Handelskonto und ein zweiter derselben
# Sekunde auf einem Earn-Konto). Zeitgleiches unter Entwuerfen bleibt Sache von "Zeitgleiche Rewards klassifizieren".
.data_activity_draft_settle_booked_collision_v1 <- function(center,editor,context,handle,now_utc,value) {
  if(identical(value$validation_status,"ready")||!is.function(center$adapter$shift_second)||!is.function(center$adapter$explain)) return(list(value=value,shifted=0L))
  entry<-.data_activity_draft_entry(center,handle)
  explanation<-tryCatch(.data_activity_draft_call(function()center$adapter$explain(context,list(entry$draft_ref)))[[1]],error=function(error)NULL)
  if(!is.list(explanation)||!identical(explanation$reason,"order_evidence_required")) return(list(value=value,shifted=0L))
  moved<-data_activity_draft_shift_past_booked_second_v1(center,context,handle,now_utc)
  if(!identical(moved$shift_status,"shifted")) return(list(value=value,shifted=0L))
  list(value=data_activity_draft_revalidate_v1(center,editor,context,handle,now_utc),shifted=moved$shift_seconds)
}

data_activity_draft_resolve_unclassified_fee_v1 <- function(center,context,draft_handle,resolution,now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(is.na(.data_activity_draft_time(now_utc))||!is.character(resolution)||length(resolution)!=1L||is.na(resolution)||!resolution%in%c("monetary_fee","asset_fee_quantity","zero_no_fee")) .data_activity_draft_abort("data_activity_draft_input_invalid")
  value<-.data_activity_draft_call(function()center$adapter$resolve_fee(context,entry$draft_ref,entry$revision,resolution,now_utc))
  entry$revision<-as.integer(value$trusted_draft$revision);entry$trusted<-value$trusted_draft;entry$confirmation<-NULL;assign(draft_handle,entry,envir=center$entries)
  .data_activity_draft_public(value,draft_handle)
}

data_activity_draft_bind_fifo_order_v1 <- function(center,context,draft_handle,fifo_order_evidence,now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(is.na(.data_activity_draft_time(now_utc))||!is.list(fifo_order_evidence)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  value<-.data_activity_draft_call(function()center$adapter$bind_fifo_order(context,entry$draft_ref,entry$revision,fifo_order_evidence,now_utc))
  entry$revision<-as.integer(value$trusted_draft$revision);entry$trusted<-value$trusted_draft;entry$confirmation<-NULL;assign(draft_handle,entry,envir=center$entries)
  .data_activity_draft_public(value,draft_handle)
}

data_activity_draft_bind_fifo_order_group_v1 <- function(center,context,draft_handle,peer_draft_handles,now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(is.na(.data_activity_draft_time(now_utc))||!is.list(peer_draft_handles)||!length(peer_draft_handles)||draft_handle%in%unlist(peer_draft_handles,use.names=FALSE)||!is.function(center$adapter$bind_fifo_order_group)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  peers<-lapply(peer_draft_handles,function(handle).data_activity_draft_entry(center,handle)$draft_ref)
  value<-.data_activity_draft_call(function()center$adapter$bind_fifo_order_group(context,entry$draft_ref,entry$revision,peers,now_utc))
  entry$revision<-as.integer(value$trusted_draft$revision);entry$trusted<-value$trusted_draft;entry$confirmation<-NULL;assign(draft_handle,entry,envir=center$entries)
  .data_activity_draft_public(value,draft_handle)
}

data_activity_draft_validate_v1 <- function(center,context,draft_handle,now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(is.na(.data_activity_draft_time(now_utc))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  value<-.data_activity_draft_call(function()center$adapter$validate(context,entry$draft_ref,entry$revision,now_utc))
  entry$revision<-as.integer(value$trusted_draft$revision);entry$trusted<-value$trusted_draft;entry$confirmation<-NULL;assign(draft_handle,entry,envir=center$entries)
  .data_activity_draft_public(value,draft_handle)
}

data_activity_draft_confirm_v1 <- function(center,context,draft_handle,now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  now<-.data_activity_draft_time(now_utc);recovery<-identical(as.integer(entry$trusted$activity_draft_version),2L)&&identical(entry$trusted$draft_state,"applying")
  if(isTRUE(entry$execution_started)) .data_activity_draft_abort("data_activity_draft_confirmation_required")
  if(is.na(now)||(!identical(entry$trusted$draft_state,"validated_ready")&&!recovery)) .data_activity_draft_abort("data_activity_draft_validation_required")
  center$sequence<-center$sequence+1L
  challenge<-paste0("adc_",substr(digest::digest(charToRaw(enc2utf8(paste(entry$trusted$validation$validation_fingerprint,center$sequence,now_utc,Sys.getpid(),sep="|"))),algo="sha256",serialize=FALSE),1L,32L))
  expires<-format(now+600,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
  entry$confirmation<-.data_activity_draft_call(function()center$adapter$confirmation(context,entry$trusted,challenge,now_utc,now_utc,expires));assign(draft_handle,entry,envir=center$entries)
  list(status="confirmed",draft_handle=draft_handle,one_use=TRUE,expires_at_utc=expires)
}

data_activity_draft_execute_v1 <- function(center,context,draft_handle,now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(is.na(.data_activity_draft_time(now_utc))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  if(is.null(entry$confirmation)) .data_activity_draft_abort("data_activity_draft_confirmation_required")
  confirmation<-entry$confirmation;entry$confirmation<-NULL;entry$execution_started<-TRUE
  assign(draft_handle,entry,envir=center$entries)
  value<-.data_activity_draft_call(function()center$adapter$apply(context,entry$draft_ref,confirmation,now_utc))
  entry$trusted<-value$trusted_draft;entry$revision<-as.integer(value$trusted_draft$revision);assign(draft_handle,entry,envir=center$entries)
  value$public_receipt
}

data_activity_draft_resume_v1 <- function(center,context,draft_handle) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  value<-.data_activity_draft_call(function()center$adapter$resume(context,entry$draft_ref));entry$trusted<-value$trusted_draft;entry$revision<-as.integer(value$trusted_draft$revision);entry$confirmation<-NULL;assign(draft_handle,entry,envir=center$entries);value$public_receipt
}

# Offen ist, was noch bearbeitet, bestaetigt oder fortgesetzt werden kann; gebuchte und abgeloeste Entwuerfe nicht.
DATA_ACTIVITY_DRAFT_OPEN_STATES_V1 <- c("editing","validated_ready","validated_blocked","applying")

# `open_only` (#420): nur offene Entwuerfe lesen. Offen ist meist nur ein kleiner Teil; jeder
# Entwurf wird einzeln gelesen, um seinen Griff zu bilden - fuer die Auswahl in der Experten-Karte braucht es nur die offenen.
data_activity_draft_refresh_v1 <- function(center,context,open_only=FALSE) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);value<-.data_activity_draft_call(function()center$adapter$list(context))
  if(!is.list(value)||!is.list(value$public_list)||!is.list(value$trusted_list)||!is.list(value$public_list$drafts)||!is.list(value$trusted_list$draft_refs)||length(value$public_list$drafts)!=length(value$trusted_list$draft_refs)) .data_activity_draft_abort("data_activity_draft_adapter_failed")
  rm(list=ls(center$entries,all.names=TRUE),envir=center$entries)
  indices<-seq_along(value$public_list$drafts)
  if(isTRUE(open_only))indices<-Filter(function(index)isTRUE(value$public_list$drafts[[index]]$status%in%DATA_ACTIVITY_DRAFT_OPEN_STATES_V1),indices)
  rows<-vector("list",length(indices))
  for(position in seq_along(indices)){index<-indices[[position]];trusted<-.data_activity_draft_call(function()center$adapter$read(context,value$trusted_list$draft_refs[[index]]))$trusted_draft;handle<-.data_activity_draft_handle(center,trusted);rows[[position]]<-c(value$public_list$drafts[[index]],list(draft_handle=handle))}
  list(status=value$public_list$status,draft_count=as.integer(value$public_list$draft_count),open_only=isTRUE(open_only),drafts=rows,path_exposed=FALSE,browser_internal_id_exposed=FALSE,fingerprint_exposed=FALSE)
}

# Die offenen Entwuerfe als Tabelle in Worten (#420): Stand, Art, Herkunft, Ereignis, Tag und - wo gelesen - der Grund einer
# Blockade. `reasons`: Ergebnis von data_activity_draft_block_reasons_v1 (je Eintrag draft_handle, title, copy).
data_activity_draft_open_frame_v1 <- function(rows,reasons=list()) {
  rows<-Filter(function(row)is.list(row)&&isTRUE(row$status%in%DATA_ACTIVITY_DRAFT_OPEN_STATES_V1),rows)
  if(!length(rows))return(data.frame())
  word<-function(table,value,fallback="")if(is.character(value)&&length(value)==1L&&!is.na(value)&&value%in%names(table))unname(table[[value]])else fallback
  states<-c(editing="in Bearbeitung",validated_ready="geprüft, nicht bestätigt",validated_blocked="blockiert",applying="unterbrochen – fortsetzen")
  actions<-c(create="Neuanlage",correct="Korrektur",void="Storno")
  origins<-c(manual_form="Formular",correction="Korrektur",tolerant_csv="Import")
  events<-c(buy="Kauf",sell="Verkauf",dividend="Dividende",stock_dividend="Stockdividende",reward="Reward",deposit="Einlieferung",withdrawal="Auslieferung",transfer="Transfer")
  day<-function(value)if(is.character(value)&&length(value)==1L&&grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$",value))paste(substr(value,9L,10L),substr(value,6L,7L),substr(value,1L,4L),sep=".")else"–"
  read<-list();for(reason in reasons)if(is.list(reason)&&is.character(reason$draft_handle))read[[reason$draft_handle]]<-reason
  why<-function(row){
    reason<-read[[row$draft_handle]]
    if(is.list(reason)&&identical(reason$status,"no_longer_blocked"))return("nicht mehr blockiert – erneut prüfen")
    if(is.list(reason)&&is.character(reason$title))return(paste(c(reason$title,if(is.character(reason$copy))reason$copy),collapse=" – "))
    missing<-unlist(row$missing_fields)
    if(length(missing))return(paste("fehlt:",paste(missing,collapse=", ")))
    if(identical(row$status,"validated_blocked"))return("Grund mit „Gründe der blockierten lesen“")
    ""
  }
  data.frame(Stand=vapply(rows,function(row)word(states,row$status,row$status),character(1L)),
             Art=vapply(rows,function(row)word(actions,row$action_type),character(1L)),
             Herkunft=vapply(rows,function(row)word(origins,row$origin_type),character(1L)),
             Ereignis=vapply(rows,function(row)word(events,row$event_summary$event_type,"–"),character(1L)),
             Tag=vapply(rows,function(row)day(row$event_summary$local_date),character(1L)),
             Grund=vapply(rows,why,character(1L)),
             stringsAsFactors=FALSE,check.names=FALSE)
}

data_activity_draft_reward_batch_v1 <- function(center,editor,context,source_fingerprint,progress_callback=NULL) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  if(!inherits(editor,"spot_data_asset_activity_editor_v1")||!is.character(source_fingerprint)||length(source_fingerprint)!=1L||is.na(source_fingerprint)||!grepl("^[a-f0-9]{64}$",source_fingerprint)||(!is.null(progress_callback)&&!is.function(progress_callback))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  selection<-.data_asset_activity_selection(editor,context)
  value<-.data_activity_draft_call(function()center$adapter$list(context))
  if(!is.list(value)||!is.list(value$public_list)||!is.list(value$trusted_list)||!is.list(value$public_list$drafts)||!is.list(value$trusted_list$draft_refs)||length(value$public_list$drafts)!=length(value$trusted_list$draft_refs)) .data_activity_draft_abort("data_activity_draft_adapter_failed")
  candidates<-which(vapply(value$public_list$drafts,function(row)is.list(row)&&identical(row$origin_type,"tolerant_csv")&&identical(row$event_summary$event_type,"reward")&&!is.null(row$source_row_ordinal),logical(1L)))
  trusted_sources<-value$trusted_list$source_fingerprints
  if(is.list(trusted_sources)&&length(trusted_sources)==length(value$trusted_list$draft_refs)){
    source_candidates<-which(vapply(trusted_sources,function(item)is.character(item)&&length(item)==1L&&!is.na(item)&&identical(item,source_fingerprint),logical(1L)))
    candidates<-intersect(candidates,source_candidates)
  }
  rows<-list();account_ids<-character()
  for(index in candidates){
    read_value<-.data_activity_draft_call(function()center$adapter$read(context,value$trusted_list$draft_refs[[index]]));trusted<-read_value$trusted_draft
    binding<-trusted$source_binding
    if(!is.list(binding)||!identical(binding$source_fingerprint,source_fingerprint))next
    handle<-.data_activity_draft_handle(center,trusted);public<-.data_activity_draft_public(read_value,handle);event<-trusted$event
    rows[[length(rows)+1L]]<-c(public,list(
      asset_ref=.data_activity_draft_ref_for_id_v1(selection,"assets",event$asset_ref),
      account_ref=.data_activity_draft_ref_for_id_v1(selection,"accounts",event$account_ref)
    ))
    account_ids<-c(account_ids,as.character(event$account_ref))
    if(!is.null(progress_callback))progress_callback(length(rows),length(candidates))
  }
  rows<-rows[order(vapply(rows,function(row)as.integer(row$source_row_ordinal),integer(1L)))]
  lifecycle<-vapply(rows,function(row)row$valuation_summary$lifecycle,character(1L))
  # Konten des Stapels nur als Attribut auf dem Server (Pruefstand je Portfolio, rc.380): nicht in den Listen, die die Oberflaeche zeigt.
  structure(list(
    status="reward_valuation_batch_ready",draft_count=as.integer(length(rows)),
    valuation_pending_count=as.integer(sum(lifecycle=="valuation_pending")),
    source_provided_count=as.integer(sum(lifecycle=="source_provided")),
    owner_manual_count=as.integer(sum(lifecycle=="owner_manual_complete")),
    market_evidence_count=as.integer(sum(lifecycle=="market_evidence_complete")),drafts=rows,
    provider_valuation_available=FALSE,canonical_write=FALSE,provider_access=FALSE,
    network_access=FALSE,path_exposed=FALSE,browser_internal_id_exposed=FALSE,
    fingerprint_exposed=FALSE
  ),account_ids=unique(account_ids))
}

.data_activity_draft_editable_fields_v1 <- function() c(
  "event_type","account_ref","related_account_ref","asset_ref","source_asset_ref",
  "event_time_evidence","local_date","local_time","time_zone",
  "original_acquired_time_evidence","original_acquired_local_date",
  "original_acquired_local_time","original_acquired_time_zone","amount_input_mode",
  "basis_evidence_mode","quantity_decimal","eligible_quantity_decimal",
  "unit_price_decimal","gross_amount_decimal","monetary_fee_decimal",
  "asset_fee_quantity_decimal","provided_basis_decimal","movement_context_code"
)

.data_activity_draft_nullable_fields_v1 <- function() c(
  "related_account_ref","source_asset_ref","local_time",
  "original_acquired_local_date","original_acquired_local_time",
  "original_acquired_time_zone","quantity_decimal","eligible_quantity_decimal","unit_price_decimal",
  "gross_amount_decimal","monetary_fee_decimal","asset_fee_quantity_decimal",
  "provided_basis_decimal"
)

.data_activity_draft_ref_for_id_v1 <- function(selection,area,identifier,optional=FALSE) {
  if(optional&&is.null(identifier))return("")
  values<-selection[[area]]$ref_by_id
  if(!is.character(identifier)||length(identifier)!=1L||is.na(identifier)||!identifier%in%names(values)) .data_activity_draft_abort("data_activity_draft_adapter_failed")
  ref<-unname(values[[identifier]])
  if(!is.character(ref)||length(ref)!=1L||is.na(ref)||!nzchar(ref)) .data_activity_draft_abort("data_activity_draft_adapter_failed")
  ref
}

data_activity_draft_open_v1 <- function(center,editor,context,draft_handle) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(!inherits(editor,"spot_data_asset_activity_editor_v1")) .data_activity_draft_abort("data_activity_draft_state_invalid")
  value<-.data_activity_draft_call(function()center$adapter$read(context,entry$draft_ref))
  entry$trusted<-value$trusted_draft;entry$revision<-as.integer(value$trusted_draft$revision);entry$confirmation<-NULL;entry$execution_started<-FALSE;assign(draft_handle,entry,envir=center$entries)
  batch<-identical(as.integer(entry$trusted$activity_draft_version),2L)
  selection<-if(batch)NULL else .data_asset_activity_selection(editor,context);event<-entry$trusted$event;public<-.data_activity_draft_public(value,draft_handle)
  list(
    status=public$status,draft_handle=draft_handle,revision=public$revision,
    origin_type=public$origin_type,action_type=public$action_type,
    selected_event_count=public$selected_event_count,
    batch_preview=if(identical(as.integer(entry$trusted$activity_draft_version),2L))entry$trusted$validation$domain_public_preview else NULL,
    validation_status=public$validation_status,missing_fields=public$missing_fields,
    issue_codes=public$issue_codes,event_summary=public$event_summary,
    source_row_ordinal=public$source_row_ordinal,source_row_key=public$source_row_key,
    unclassified_fee_summary=public$unclassified_fee_summary,
    valuation_summary=public$valuation_summary,
    portfolio_ref=if(batch)''else .data_activity_draft_ref_for_id_v1(selection,"portfolios",entry$trusted$portfolio_id),
    account_ref=.data_activity_draft_ref_for_id_v1(selection,"accounts",event$account_ref,optional=TRUE),
    related_account_ref=.data_activity_draft_ref_for_id_v1(selection,"accounts",event$related_account_ref,optional=TRUE),
    asset_ref=.data_activity_draft_ref_for_id_v1(selection,"assets",event$asset_ref,optional=TRUE),
    source_asset_ref=.data_activity_draft_ref_for_id_v1(selection,"assets",event$source_asset_ref,optional=TRUE),
    can_edit=public$status%in%c("editing","validated_blocked","validated_ready")&&!identical(as.integer(entry$trusted$activity_draft_version),2L),
    can_resolve_unclassified_fee=isTRUE(public$can_resolve_unclassified_fee),
    can_confirm=isTRUE(public$can_confirm),can_resume=isTRUE(public$can_resume),
    canonical_write=FALSE,path_exposed=FALSE,browser_internal_id_exposed=FALSE,fingerprint_exposed=FALSE
  )
}

data_activity_draft_patch_field_v1 <- function(center,editor,context,draft_handle,field_name,operation,value="",now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(!inherits(editor,"spot_data_asset_activity_editor_v1")||!is.character(field_name)||length(field_name)!=1L||is.na(field_name)||!field_name%in%.data_activity_draft_editable_fields_v1()||!is.character(operation)||length(operation)!=1L||is.na(operation)||!operation%in%c("set_value","set_null","remove")||is.na(.data_activity_draft_time(now_utc))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  patch<-list();remove<-character()
  if(identical(operation,"remove")){remove<-field_name}else if(identical(operation,"set_null")){
    if(!field_name%in%.data_activity_draft_nullable_fields_v1()) .data_activity_draft_abort("data_activity_draft_input_invalid")
    patch[field_name]<-list(NULL)
  }else{
    if(!is.character(value)||length(value)!=1L||is.na(value)||!nzchar(value)||value!=trimws(value)||nchar(value,type="bytes")>512L||grepl("[[:cntrl:]]",value)) .data_activity_draft_abort("data_activity_draft_input_invalid")
    selection<-.data_asset_activity_selection(editor,context)
    if(field_name%in%c("account_ref","related_account_ref"))value<-.data_asset_activity_resolve(selection,"accounts",value)$account_id
    if(field_name%in%c("asset_ref","source_asset_ref"))value<-.data_asset_activity_resolve(selection,"assets",value)$asset_id
    patch[[field_name]]<-value
  }
  data_activity_draft_update_v1(center,context,draft_handle,patch,remove,now_utc)
}

.data_activity_draft_time_patch_v1 <- function(center,context,event) {
  patch<-list();remove<-character();set_null<-function(field)patch[field]<<-list(NULL);set_value<-function(field,value)patch[[field]]<<-value;drop<-function(field)remove<<-unique(c(remove,field))
  mode<-event$event_time_evidence
  if(identical(mode,"exact")){
    complete<-all(vapply(c("local_date","local_time","time_zone"),function(field)is.character(event[[field]])&&length(event[[field]])==1L&&nzchar(event[[field]]),logical(1L)))
    if(complete)set_value("effective_at_utc",.data_activity_draft_call(function()center$adapter$resolve_time(context,event$local_date,event$local_time,event$time_zone))$effective_at_utc)else drop("effective_at_utc")
  }else if(identical(mode,"date_only")){set_null("local_time");set_null("effective_at_utc")}else drop("effective_at_utc")
  original<-event$original_acquired_time_evidence
  if(identical(original,"exact")){
    complete<-all(vapply(c("original_acquired_local_date","original_acquired_local_time","original_acquired_time_zone"),function(field)is.character(event[[field]])&&length(event[[field]])==1L&&nzchar(event[[field]]),logical(1L)))
    if(complete)set_value("original_acquired_at_utc",.data_activity_draft_call(function()center$adapter$resolve_time(context,event$original_acquired_local_date,event$original_acquired_local_time,event$original_acquired_time_zone))$effective_at_utc)else drop("original_acquired_at_utc")
  }else if(identical(original,"date_only")){set_null("original_acquired_local_time");set_null("original_acquired_at_utc")}else if(identical(original,"not_applicable")){for(field in c("original_acquired_local_date","original_acquired_local_time","original_acquired_time_zone","original_acquired_at_utc"))set_null(field)}else drop("original_acquired_at_utc")
  remove<-setdiff(remove,names(patch));list(patch=patch,remove=remove)
}

data_activity_draft_set_market_reward_valuation_v1 <- function(center,service,context,draft_handle,confirmed,now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(!is.list(service)||!is.function(service$apply)||!isTRUE(confirmed)||is.na(.data_activity_draft_time(now_utc))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  value<-.data_activity_draft_call(function()service$apply(entry$draft_ref,TRUE,now_utc))
  entry$revision<-as.integer(value$trusted_draft$revision);entry$trusted<-value$trusted_draft;entry$confirmation<-NULL;assign(draft_handle,entry,envir=center$entries)
  .data_activity_draft_public(value,draft_handle)
}

data_activity_draft_preview_reward_market_batch_v1 <- function(center,service,context,batch) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  if(!is.list(service)||!is.function(service$preview)||!is.list(batch)||!identical(batch$status,"reward_valuation_batch_ready")||!is.list(batch$drafts)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  pending<-Filter(function(row)is.list(row)&&identical(row$valuation_summary$lifecycle,"valuation_pending"),batch$drafts)
  dispositions<-lapply(pending,function(row)tryCatch({
    entry<-.data_activity_draft_entry(center,row$draft_handle);.data_activity_draft_call(function()service$preview(entry$draft_ref))
    list(source_row_ordinal=row$source_row_ordinal,disposition="valuation_ready",draft_handle=row$draft_handle,error_code=NULL)
  },error=function(error)list(source_row_ordinal=row$source_row_ordinal,disposition="valuation_blocked",draft_handle=NULL,error_code=if(is.null(error$code))"data_reward_daily_close_boundary_failed"else error$code)))
  ready<-Filter(function(row)identical(row$disposition,"valuation_ready"),dispositions)
  list(contract_version="statement_reward_market_batch_preview_v1",status=if(length(ready))"confirmation_required"else"nothing_to_apply",candidate_count=length(pending),ready_count=length(ready),blocked_count=length(pending)-length(ready),silent_drop_count=0L,canonical_write=FALSE,provider_access=FALSE,network_access=FALSE,activity_draft_handles=lapply(ready,`[[`,"draft_handle"),source_row_ordinals=lapply(ready,`[[`,"source_row_ordinal"),dispositions=dispositions)
}

data_activity_draft_apply_reward_market_batch_v1 <- function(center,service,context,preview,confirmed,now_utc,progress_callback=NULL) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  if(!is.list(service)||!is.function(service$apply)||!is.list(preview)||!identical(preview$status,"confirmation_required")||!isTRUE(confirmed)||is.na(.data_activity_draft_time(now_utc))||length(preview$activity_draft_handles)!=preview$ready_count||(!is.null(progress_callback)&&!is.function(progress_callback))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  dispositions<-vector("list",preview$ready_count)
  for(index in seq_len(preview$ready_count)){
    handle<-preview$activity_draft_handles[[index]]
    dispositions[[index]]<-tryCatch({data_activity_draft_set_market_reward_valuation_v1(center,service,context,handle,TRUE,now_utc);list(source_row_ordinal=preview$source_row_ordinals[[index]],disposition="valuation_applied",error_code=NULL)},error=function(error)list(source_row_ordinal=preview$source_row_ordinals[[index]],disposition="valuation_failed",error_code=if(is.null(error$code))"data_reward_daily_close_boundary_failed"else error$code))
    if(!is.null(progress_callback))progress_callback(index,preview$ready_count)
  }
  applied<-sum(vapply(dispositions,function(row)identical(row$disposition,"valuation_applied"),logical(1L)))
  list(contract_version="statement_reward_market_batch_result_v1",status=if(applied==preview$ready_count)"complete"else"partial",candidate_count=preview$candidate_count,valuation_applied_count=applied,blocked_count=preview$blocked_count+preview$ready_count-applied,silent_drop_count=0L,canonical_write=FALSE,provider_access=FALSE,network_access=FALSE,dispositions=c(preview$dispositions[!vapply(preview$dispositions,function(row)identical(row$disposition,"valuation_ready"),logical(1L))],dispositions))
}

data_activity_draft_preview_reward_batch_validation_v1 <- function(center,batch) {
  .data_activity_draft_check(center)
  if(!is.list(batch)||!identical(batch$status,"reward_valuation_batch_ready")||!is.list(batch$drafts)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  complete<-c("source_provided","owner_manual_complete","market_evidence_complete")
  rows<-Filter(function(row)is.list(row)&&row$valuation_summary$lifecycle%in%complete&&!identical(row$validation_status,"ready"),batch$drafts)
  list(contract_version="statement_reward_batch_validation_preview_v1",status=if(length(rows))"confirmation_required"else"nothing_to_validate",candidate_count=length(rows),silent_drop_count=0L,canonical_write=FALSE,activity_draft_handles=lapply(rows,`[[`,"draft_handle"),source_row_ordinals=lapply(rows,`[[`,"source_row_ordinal"))
}

data_activity_draft_apply_reward_batch_validation_v1 <- function(center,editor,context,preview,confirmed,now_utc,progress_callback=NULL) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  if(!inherits(editor,"spot_data_asset_activity_editor_v1")||!is.list(preview)||!identical(preview$status,"confirmation_required")||!isTRUE(confirmed)||is.na(.data_activity_draft_time(now_utc))||length(preview$activity_draft_handles)!=preview$candidate_count||(!is.null(progress_callback)&&!is.function(progress_callback))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  dispositions<-vector("list",preview$candidate_count)
  for(index in seq_len(preview$candidate_count)){
    handle<-preview$activity_draft_handles[[index]]
    dispositions[[index]]<-tryCatch({
      entry<-.data_activity_draft_entry(center,handle);nullable<-c("asset_fee_quantity_decimal","eligible_quantity_decimal","gross_amount_decimal","monetary_fee_decimal","related_account_ref","source_asset_ref");missing<-setdiff(nullable,names(entry$trusted$event))
      if(length(missing)){patch<-stats::setNames(rep(list(NULL),length(missing)),missing);data_activity_draft_update_v1(center,context,handle,patch,character(),now_utc)}
      settled<-.data_activity_draft_settle_booked_collision_v1(center,editor,context,handle,now_utc,data_activity_draft_revalidate_v1(center,editor,context,handle,now_utc));value<-settled$value
      list(source_row_ordinal=preview$source_row_ordinals[[index]],disposition=if(identical(value$validation_status,"ready"))"validated_ready"else"validation_blocked",validation_status=value$validation_status,missing_fields=value$missing_fields,shifted_seconds=settled$shifted,error_code=NULL)
    },error=function(error)list(source_row_ordinal=preview$source_row_ordinals[[index]],disposition="validation_failed",validation_status=NULL,missing_fields=list(),error_code=if(is.null(error$code))"data_activity_draft_adapter_failed"else error$code))
    # Jede Revalidierung rechnet eine eigene FIFO-Vorschau und braucht einige
    # Sekunden. Ohne Meldung schweigt die Oberflaeche bei einem grossen Import viele
    # Minuten, und die Browserverbindung bricht ab (#422).
    if(!is.null(progress_callback))progress_callback(index,preview$candidate_count)
  }
  list(contract_version="statement_reward_batch_validation_result_v1",status=if(all(vapply(dispositions,function(row)identical(row$disposition,"validated_ready"),logical(1L))))"complete"else"partial",candidate_count=preview$candidate_count,validated_ready_count=sum(vapply(dispositions,function(row)identical(row$disposition,"validated_ready"),logical(1L))),blocked_count=sum(vapply(dispositions,function(row)!identical(row$disposition,"validated_ready"),logical(1L))),silent_drop_count=0L,canonical_write=FALSE,dispositions=dispositions,shifted_count=sum(vapply(dispositions,function(row)isTRUE(row$shifted_seconds>0L),logical(1L))))
}

data_activity_draft_preview_reward_collision_batch_v1 <- function(center,batch) {
  .data_activity_draft_check(center)
  if(!is.list(batch)||!identical(batch$status,"reward_valuation_batch_ready")||!is.list(batch$drafts)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  complete<-c("source_provided","owner_manual_complete","market_evidence_complete")
  blocked<-Filter(function(row){if(!is.list(row)||!row$valuation_summary$lifecycle%in%complete||identical(row$status,"committed"))return(FALSE);entry<-.data_activity_draft_entry(center,row$draft_handle);group<-entry$trusted$source_auxiliary$fifo_order_evidence;identical(row$validation_status,"blocked")||(identical(row$validation_status,"not_validated")&&is.list(group)&&length(group)>=2L)},batch$drafts)
  committed<-Filter(function(row)is.list(row)&&identical(row$status,"committed"),batch$drafts)
  event_for<-function(row).data_activity_draft_entry(center,row$draft_handle)$trusted$event
  economic_keys<-c("event_type","asset_ref","account_ref","effective_at_utc","quantity_decimal","gross_amount_decimal","monetary_fee_decimal","asset_fee_quantity_decimal")
  dispositions<-lapply(blocked,function(row){event<-event_for(row);matches<-Filter(function(other){candidate<-event_for(other);identical(candidate$asset_ref,event$asset_ref)&&identical(candidate$effective_at_utc,event$effective_at_utc)},committed);exact<-Filter(function(other)identical(event[economic_keys],event_for(other)[economic_keys]),matches);classification<-if(length(exact))"probable_duplicate"else if(length(matches))"distinct_same_time"else"unresolved_domain_block";list(source_row_ordinal=row$source_row_ordinal,classification=classification,draft_handle=if(classification=="distinct_same_time")row$draft_handle else NULL,peer_draft_handles=if(classification=="distinct_same_time")lapply(matches,`[[`,"draft_handle") else NULL)})
  distinct<-Filter(function(row)identical(row$classification,"distinct_same_time"),dispositions)
  list(contract_version="statement_reward_collision_batch_preview_v1",status=if(length(distinct))"confirmation_required"else"nothing_to_bind",candidate_count=length(blocked),exact_replay_count=length(committed),distinct_same_time_count=length(distinct),probable_duplicate_count=sum(vapply(dispositions,function(row)identical(row$classification,"probable_duplicate"),logical(1L))),unresolved_count=sum(vapply(dispositions,function(row)identical(row$classification,"unresolved_domain_block"),logical(1L))),silent_drop_count=0L,canonical_write=FALSE,dispositions=dispositions)
}

data_activity_draft_apply_reward_collision_batch_v1 <- function(center,editor,context,preview,confirmed,now_utc,progress_callback=NULL) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  if(!inherits(editor,"spot_data_asset_activity_editor_v1")||!is.list(preview)||!identical(preview$status,"confirmation_required")||!isTRUE(confirmed)||is.na(.data_activity_draft_time(now_utc))||(!is.null(progress_callback)&&!is.function(progress_callback))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  selected<-Filter(function(row)identical(row$classification,"distinct_same_time"),preview$dispositions);rows<-vector("list",length(selected))
  for(index in seq_along(selected)){row<-selected[[index]];rows[[index]]<-tryCatch({entry<-.data_activity_draft_entry(center,row$draft_handle);group<-entry$trusted$source_auxiliary$fifo_order_evidence;if(!is.list(group)||length(group)<2L)data_activity_draft_bind_fifo_order_group_v1(center,context,row$draft_handle,row$peer_draft_handles,now_utc);validated<-data_activity_draft_revalidate_v1(center,editor,context,row$draft_handle,now_utc);list(source_row_ordinal=row$source_row_ordinal,disposition=if(identical(validated$validation_status,"ready"))"source_order_group_ready"else"source_order_group_blocked",error_code=NULL)},error=function(error)list(source_row_ordinal=row$source_row_ordinal,disposition="source_order_group_failed",error_code=if(is.null(error$code))"data_activity_draft_adapter_failed"else error$code));if(!is.null(progress_callback))progress_callback(index,length(selected))}
  ready<-sum(vapply(rows,function(row)identical(row$disposition,"source_order_group_ready"),logical(1L)))
  list(contract_version="statement_reward_collision_batch_result_v1",status=if(ready==length(selected))"complete"else"partial",candidate_count=preview$candidate_count,source_order_group_ready_count=ready,blocked_count=preview$candidate_count-ready,silent_drop_count=0L,canonical_write=FALSE,rows=rows)
}

data_activity_draft_preview_reward_canonical_batch_v1 <- function(center,batch) {
  .data_activity_draft_check(center)
  if(!is.list(batch)||!identical(batch$status,"reward_valuation_batch_ready")||!is.list(batch$drafts)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  complete<-c("source_provided","owner_manual_complete","market_evidence_complete")
  rows<-Filter(function(row)is.list(row)&&row$valuation_summary$lifecycle%in%complete&&identical(row$validation_status,"ready")&&!identical(row$status,"committed"),batch$drafts)
  list(contract_version="statement_reward_canonical_batch_preview_v1",status=if(length(rows))"confirmation_required"else"nothing_to_commit",candidate_count=length(rows),silent_drop_count=0L,canonical_write=length(rows)>0L,fifo_revalidation_required=length(rows)>0L,activity_draft_handles=lapply(rows,`[[`,"draft_handle"),source_row_ordinals=lapply(rows,`[[`,"source_row_ordinal"))
}

data_activity_draft_apply_reward_canonical_batch_v1 <- function(center,editor,context,preview,confirmed,now_utc,progress_callback=NULL) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  if(!inherits(editor,"spot_data_asset_activity_editor_v1")||!is.list(preview)||!identical(preview$status,"confirmation_required")||!isTRUE(confirmed)||is.na(.data_activity_draft_time(now_utc))||length(preview$activity_draft_handles)!=preview$candidate_count||(!is.null(progress_callback)&&!is.function(progress_callback))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  dispositions<-vector("list",preview$candidate_count)
  for(index in seq_len(preview$candidate_count)){
    handle<-preview$activity_draft_handles[[index]]
    dispositions[[index]]<-tryCatch({
      settled<-.data_activity_draft_settle_booked_collision_v1(center,editor,context,handle,now_utc,data_activity_draft_revalidate_v1(center,editor,context,handle,now_utc));validated<-settled$value
      if(!identical(validated$validation_status,"ready"))list(source_row_ordinal=preview$source_row_ordinals[[index]],disposition="revalidation_blocked",activity_generation_updated=FALSE,shifted_seconds=settled$shifted,error_code=NULL)
      else{data_activity_draft_confirm_v1(center,context,handle,now_utc);receipt<-data_activity_draft_execute_v1(center,context,handle,now_utc);list(source_row_ordinal=preview$source_row_ordinals[[index]],disposition=if(identical(receipt$draft_status,"committed")&&isTRUE(receipt$activity_generation_updated))"canonical_committed"else"canonical_write_incomplete",activity_generation_updated=isTRUE(receipt$activity_generation_updated),shifted_seconds=settled$shifted,error_code=NULL)}
    },error=function(error)list(source_row_ordinal=preview$source_row_ordinals[[index]],disposition="canonical_failed",activity_generation_updated=FALSE,error_code=if(is.null(error$code))"data_activity_draft_adapter_failed"else error$code))
    # Buchen ist je Reward noch teurer als Pruefen - Revalidierung,
    # Bestaetigung und Schreiben, bei einem grossen Import also viele Minuten fuer alle
    # Rewards. Jeder Reward wird einzeln festgeschrieben: ein Abbruch verliert
    # nur den laufenden, und die schon gebuchten erkennt der naechste Anlauf
    # ueber den Quellschluessel wieder (05.10.2026, #422).
    if(!is.null(progress_callback))progress_callback(index,preview$candidate_count)
  }
  committed<-sum(vapply(dispositions,function(row)identical(row$disposition,"canonical_committed"),logical(1L)))
  list(contract_version="statement_reward_canonical_batch_result_v1",status=if(committed==preview$candidate_count)"complete"else"partial",candidate_count=preview$candidate_count,canonical_committed_count=committed,blocked_count=preview$candidate_count-committed,activity_generation_updated_count=sum(vapply(dispositions,function(row)isTRUE(row$activity_generation_updated),logical(1L))),silent_drop_count=0L,canonical_write=committed>0L,fifo_revalidated_before_each_write=TRUE,dispositions=dispositions,shifted_count=sum(vapply(dispositions,function(row)isTRUE(row$shifted_seconds>0L),logical(1L))))
}

data_activity_draft_preview_market_reward_valuation_v1 <- function(center,service,context,draft_handle) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(!is.list(service)||!is.function(service$preview)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  .data_activity_draft_call(function()service$preview(entry$draft_ref))
}

# Ein Wert von Hand (#520): Komma als Dezimalzeichen, Punkte davor als Tausendertrenner, Leerzeichen und Nullen am Ende. Der Kern nimmt
# nur die kanonische Form ("10", nicht "10.00" oder "10,00") und lehnte den Reward sonst mit asset_activity_amount_invalid ab.
.data_activity_draft_decimal_input_v1 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value)) return(value)
  text <- gsub("[[:space:]]", "", value)
  if (grepl(",", text, fixed = TRUE)) text <- gsub(",", ".", gsub(".", "", text, fixed = TRUE), fixed = TRUE)
  if (grepl("^[0-9]+\\.[0-9]+$", text)) text <- sub("\\.$", "", sub("0+$", "", text))
  if (grepl("^0[0-9]", text)) text <- sub("^0+([0-9])", "\\1", text)
  text
}
data_activity_draft_set_manual_reward_valuation_v1 <- function(center,mapping_center,context,draft_handle,mode,value_decimal,price_currency,now_utc) {
  value_decimal<-.data_activity_draft_decimal_input_v1(value_decimal)
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  evidence<-entry$trusted$source_auxiliary$valuation_evidence;event<-entry$trusted$event
  if(!is.list(mapping_center)||!is.function(mapping_center$derive_reward_manual_valuation)||!is.list(evidence)||!identical(evidence$valuation_origin,"source_missing")||!identical(event$event_type,"reward")||!mode%in%c("manual_unit_price","manual_fiat_total")||!is.character(value_decimal)||length(value_decimal)!=1L||is.na(value_decimal)||!grepl("^(0|[1-9][0-9]*)(\\.[0-9]+)?$",value_decimal)||!is.character(price_currency)||length(price_currency)!=1L||is.na(price_currency)||is.na(.data_activity_draft_time(now_utc))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  projection<-.data_activity_draft_call(function()mapping_center$derive_reward_manual_valuation(
    event$quantity_decimal,event$asset_fee_quantity_decimal,mode,value_decimal,
    price_currency,evidence$price_currency
  ))
  data_activity_draft_update_v1(center,context,draft_handle,projection$event_patch,character(),now_utc)
}

data_activity_draft_revalidate_v1 <- function(center,editor,context,draft_handle,now_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context);entry<-.data_activity_draft_entry(center,draft_handle)
  if(!inherits(editor,"spot_data_asset_activity_editor_v1")||is.na(.data_activity_draft_time(now_utc))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  normalized<-.data_activity_draft_time_patch_v1(center,context,entry$trusted$event)
  invisible(data_activity_draft_update_v1(center,context,draft_handle,normalized$patch,normalized$remove,now_utc))
  data_activity_draft_validate_v1(center,context,draft_handle,now_utc)
}

# Offene Reward-Entwuerfe, gruppiert nach der Quelldatei, die sie erzeugt hat.
# Gelesen wird allein die Entwurfsliste des Datenraums - kein Statement, keine
# Datei, keine Sitzung. Damit ueberlebt der Importstand einen
# Verbindungsabbruch: ohne diese Uebersicht stand die Karte wieder auf
# Schritt 1, obwohl Entwuerfe im Datenraum lagen, viele davon fertig geprueft
# (#422). Die Boerse je Gruppe kostet einen einzigen Read,
# weil die Entwurfsliste den Adapter nicht ausweist.
# Die Gruende blockierter Entwuerfe, je Entwurf ein Satz (#420). Ein blockierter
# Entwurf trug bisher nur activity_draft_domain_invalid; im gefuehrten Import stand
# dazu, er sei "zeitgleich mit anderen Rewards" - auch wenn es an der Mengenskala
# lag. Gelesen wird der Grund aus derselben Pruefung, in
# einem Aufruf fuer alle; geschrieben wird nichts. Konto und Asset erscheinen mit
# ihrer Bezeichnung aus der Auswahl der Sitzung, nie mit ihrer Kennung.
data_activity_draft_block_reasons_v1 <- function(center,editor,context,draft_handles) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  if(!is.character(draft_handles)||!length(draft_handles)||length(draft_handles)>200L||anyNA(draft_handles)||anyDuplicated(draft_handles)) .data_activity_draft_abort("data_activity_draft_input_invalid")
  refs<-vapply(draft_handles,function(handle).data_activity_draft_entry(center,handle)$draft_ref,character(1L),USE.NAMES=FALSE)
  explanations<-.data_activity_draft_call(function()center$adapter$explain(context,refs))
  if(!is.list(explanations)||length(explanations)!=length(refs)) .data_activity_draft_abort("data_activity_draft_adapter_failed")
  selection<-tryCatch(.data_asset_activity_selection(editor,context),error=function(error)NULL)
  label<-function(kind,internal_id){area<-selection[[paste0(kind,"s")]];ref<-unname(area$ref_by_id[[internal_id]]);if(is.null(ref))NULL else area$by_ref[[ref]]$label}
  lapply(seq_along(refs),function(index){
    explanation<-explanations[[index]]
    c(list(draft_handle=draft_handles[[index]],status=explanation$status,reason=explanation$reason),data_activity_block_reason_text_v1(explanation,label))
  })
}

# Erledigten Lauf stilllegen (#520): Vorschau liest nur und nennt die Zahl der Entwuerfe; Anwenden schreibt die gezeigte Vorschau.
data_activity_draft_retire_preview_v1 <- function(center,context,group,previewed_at_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  by_owner<-is.list(group)&&isTRUE(group$retire_by_owner)
  if(!is.list(group)||(!by_owner&&(!is.character(group$retire_replacement)||length(group$retire_replacement)!=1L||is.na(group$retire_replacement)))||is.na(.data_activity_draft_time(previewed_at_utc)))
    .data_activity_draft_abort("data_activity_draft_input_invalid")
  # Von Hand erledigt: Ersatz gleich Quelle - die Bruecke bildet daraus die Markierung "vom Eigentuemer erledigt".
  replacement<-if(by_owner)group$source_fingerprint else group$retire_replacement
  value<-.data_activity_draft_call(function()center$adapter$retire_preview(context,group$source_fingerprint,replacement,group$total,group$committed,previewed_at_utc))
  if(!is.list(value)||!value$mode%in%c("supersession","mixed_source_retirement")||!is.character(value$trusted_preview_token)) .data_activity_draft_abort("data_activity_draft_adapter_failed")
  list(mode=value$mode,by_owner=by_owner,draft_count=as.integer(group$total),committed_count=as.integer(group$committed),open_count=as.integer(group$total-group$committed),
    trusted_preview_token=value$trusted_preview_token)
}
data_activity_draft_retire_apply_v1 <- function(center,context,preview,confirmed_at_utc) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  if(!is.list(preview)||!is.character(preview$trusted_preview_token)||is.na(.data_activity_draft_time(confirmed_at_utc))) .data_activity_draft_abort("data_activity_draft_input_invalid")
  value<-.data_activity_draft_call(function()center$adapter$retire_apply(context,preview$mode,preview$trusted_preview_token,confirmed_at_utc))
  if(!is.list(value)||!identical(value$status,"activity_draft_retired")) .data_activity_draft_abort("data_activity_draft_adapter_failed")
  invisible(value)
}

data_activity_draft_reward_sources_v1 <- function(center,context,read_adapter_label=TRUE) {
  .data_activity_draft_check(center);.data_activity_draft_context(context)
  value<-.data_activity_draft_call(function()center$adapter$list(context))
  if(!is.list(value)||!is.list(value$public_list)||!is.list(value$trusted_list)||!is.list(value$public_list$drafts)||!is.list(value$trusted_list$draft_refs)||length(value$public_list$drafts)!=length(value$trusted_list$draft_refs)) .data_activity_draft_abort("data_activity_draft_adapter_failed")
  fingerprints<-value$trusted_list$source_fingerprints
  if(!is.list(fingerprints)||length(fingerprints)!=length(value$trusted_list$draft_refs)) return(list())
  # Die Adapterkennung je Entwurf steht seit rc.230 in der Liste. Vorher wurde je
  # offenem Lauf ein Entwurf einzeln nachgelesen, und jeder Einzelabruf prueft
  # den ganzen Abloesestand: mehrere Laeufe kosteten Sekunden.
  # Fehlt die Angabe - etwa bei einer aelteren Liste -, wird wie bisher gelesen.
  adapter_ids<-value$trusted_list$source_adapter_ids
  adapter_ids_listed<-is.list(adapter_ids)&&length(adapter_ids)==length(value$trusted_list$draft_refs)
  complete<-c("source_provided","owner_manual_complete","market_evidence_complete")
  # Storno (#509): Eine stornierte Buchung deckt nur Entwuerfe, die vor dem Storno entstanden sind - Reste eines Laufs, der
  # storniert und anders neu gebucht wurde. Was nach dem Storno eingelesen wird, ist neu: Wer Rewards storniert, um sie
  # auf ein anderes Konto neu einzulesen, soll den neuen Lauf buchen koennen, nicht stilllegen. Fehlen die Angaben (aeltere Liste),
  # gilt jede Buchung wie bisher.
  zeit_je_entwurf<-function(name){
    werte<-value$trusted_list[[name]]
    if(!is.list(werte)||length(werte)!=length(value$trusted_list$draft_refs))return(rep(NA_character_,length(value$trusted_list$draft_refs)))
    vapply(werte,function(item)if(is.character(item)&&length(item)==1L&&!is.na(item))item else NA_character_,character(1L))
  }
  erstellt_je_entwurf<-zeit_je_entwurf("created_at_utc");storniert_je_entwurf<-zeit_je_entwurf("committed_voided_at_utc")
  groups<-list();gebuchte_kennungen<-character();gebuchte_quellen<-character();gebuchte_bis<-character()
  for(index in seq_along(value$public_list$drafts)){
    row<-value$public_list$drafts[[index]];fingerprint<-fingerprints[[index]]
    if(!is.list(row)||!identical(row$origin_type,"tolerant_csv")||!identical(row$event_summary$event_type,"reward")) next
    if(!is.character(fingerprint)||length(fingerprint)!=1L||is.na(fingerprint)) next
    # Erledigte und ersetzte Entwuerfe zaehlen, geben aber keinen Anlass zum
    # Fortsetzen; eine Gruppe erscheint nur, wenn noch etwas offen ist.
    bucket<-if(identical(row$status,"committed"))"committed" else if(identical(row$status,"superseded"))"superseded" else if(identical(row$valuation_summary$lifecycle,"valuation_pending"))"pending" else if(identical(row$validation_status,"ready"))"ready" else if(identical(row$validation_status,"blocked"))"blocked" else "unvalidated"
    current<-groups[[fingerprint]]
    if(is.null(current))current<-list(source_fingerprint=fingerprint,draft_ref=value$trusted_list$draft_refs[[index]],listed_adapter_id=if(adapter_ids_listed)adapter_ids[[index]] else NULL,total=0L,ready=0L,pending=0L,blocked=0L,unvalidated=0L,committed=0L,superseded=0L,first_date=NA_character_,last_date=NA_character_,identities=character(),open_identities=character(),created=character(),open_created=character())
    current$total<-current$total+1L;current[[bucket]]<-current[[bucket]]+1L
    # Wirtschaftliche Kennung aus dem, was die Entwurfsliste ohnehin hergibt.
    # Damit laesst sich feststellen, ob ein Lauf vollstaendig in einem anderen
    # steckt: Datum, Uhrzeit und Menge sind je Lauf
    # eindeutig und liefern dasselbe Ergebnis wie Asset, Konto, Wirkzeit, Menge.
    kennung<-paste(as.character(row$event_summary$local_date),as.character(row$event_summary$local_time),
      as.character(row$event_summary$quantity_decimal),sep="|")
    current$identities<-c(current$identities,kennung);current$created<-c(current$created,erstellt_je_entwurf[[index]])
    if(!bucket%in%c("committed","superseded")){current$open_identities<-c(current$open_identities,kennung);current$open_created<-c(current$open_created,erstellt_je_entwurf[[index]])}
    # Gebuchte Kennungen zaehlen gruppenuebergreifend: ein Altlauf ist auch dann
    # erledigt, wenn der deckende Lauf schon gebucht und damit aus der Uebersicht
    # verschwunden ist.
    if(identical(bucket,"committed")){gebuchte_kennungen<-c(gebuchte_kennungen,kennung);gebuchte_quellen<-c(gebuchte_quellen,fingerprint);gebuchte_bis<-c(gebuchte_bis,storniert_je_entwurf[[index]])}
    local_date<-row$event_summary$local_date
    if(is.character(local_date)&&length(local_date)==1L&&!is.na(local_date)){
      if(is.na(current$first_date)||local_date<current$first_date)current$first_date<-local_date
      if(is.na(current$last_date)||local_date>current$last_date)current$last_date<-local_date
    }
    groups[[fingerprint]]<-current
  }
  open<-Filter(function(group)group$ready+group$pending+group$blocked+group$unvalidated>0L,groups)
  if(!length(open))return(list())
  open<-lapply(open,function(group){
    group$adapter_id<-if(!isTRUE(read_adapter_label))NA_character_ else if(adapter_ids_listed){
      label<-group$listed_adapter_id
      if(is.character(label)&&length(label)==1L&&!is.na(label))label else NA_character_
    } else tryCatch({
      trusted<-.data_activity_draft_call(function()center$adapter$read(context,group$draft_ref))$trusted_draft
      label<-trusted$source_auxiliary$valuation_evidence$adapter_id
      if(is.character(label)&&length(label)==1L&&!is.na(label))label else NA_character_
    },error=function(error)NA_character_)
    group$draft_ref<-NULL;group$listed_adapter_id<-NULL;group
  })
  open<-unname(open[order(vapply(open,function(group)group$total,integer(1L)),decreasing=TRUE)])
  # Welche Buchungen decken eine Kennung, die zur Zeit `erstellt` entstand? Eine stehende immer, eine stornierte nur danach.
  deckt_ab<-function(kennung,erstellt)gebuchte_kennungen==kennung&(is.na(gebuchte_bis)|(!is.na(erstellt)&gebuchte_bis>erstellt))
  gedeckt<-function(kennungen,erstellt,quellen=NULL)vapply(seq_along(kennungen),function(i){
    treffer<-deckt_ab(kennungen[[i]],erstellt[[i]]);if(!is.null(quellen))treffer<-treffer&gebuchte_quellen%in%quellen;any(treffer)},logical(1L))
  # Ein Lauf, dessen Rewards restlos in einem groesseren stecken, ist erledigt.
  # Ohne diese Angabe standen mehrere Laeufe gleichberechtigt nebeneinander, manche ueberfluessig, und die Karte forderte auch bei
  # diesen zum Handeln auf - nicht erkennbar, welcher gilt
  # (#422).
  for(index in seq_along(open)){
    eigene<-open[[index]]$identities
    deckend<-NA_integer_;gebucht<-FALSE
    # Zuerst: steckt jeder Reward dieses Laufs schon in einer Buchung? Dann ist er
    # erledigt, ganz gleich aus welchem Lauf die Buchung stammt.
    if(length(eigene)&&all(gedeckt(eigene,open[[index]]$created)))gebucht<-TRUE
    else for(other in seq_along(open)){
      if(other==index||open[[other]]$total<=open[[index]]$total)next
      if(all(eigene%in%open[[other]]$identities)){deckend<-other;break}
    }
    open[[index]]$already_booked<-gebucht
    open[[index]]$covered_by<-if(gebucht)0L else deckend
    open[[index]]$covered_by_total<-if(gebucht)NA_integer_ else if(is.na(deckend))NA_integer_ else open[[deckend]]$total
    # Stilllegen (#520) braucht einen Ersatzlauf, der die offenen Rewards dieses Laufs traegt: den deckenden Lauf oder die Laeufe, in
    # denen sie gebucht sind. Ohne eigene Buchung loest er ihn ab, mit eigenen Buchungen bleiben diese erhalten. Der Quell-
    # Fingerprint bleibt wie bisher serverseitig. Sind die Rewards ueber mehrere Laeufe gebucht (viele Entwuerfe,
    # gebucht in mehreren spaeteren Laeufen), steht der kleinste Fingerprint fuer alle; der Kern vermerkt den Ersatz nur.
    ersatz<-if(!is.na(deckend))open[[deckend]]$source_fingerprint else if(gebucht){
      treffer<-Reduce(`|`,Map(deckt_ab,open[[index]]$open_identities,open[[index]]$open_created),rep(FALSE,length(gebuchte_kennungen)))
      quellen<-setdiff(unique(gebuchte_quellen[treffer]),open[[index]]$source_fingerprint)
      if(length(quellen)&&all(gedeckt(open[[index]]$open_identities,open[[index]]$open_created,quellen)))sort(quellen)[[1L]] else NA_character_
    } else NA_character_
    open[[index]]$retire_replacement<-if(open[[index]]$superseded==0L)ersatz else NA_character_
    # Bleiben nur blockierte oder unbewertete Rewards, kann der Eigentuemer sie von Hand buchen und den Rest stilllegen (#520).
    rest<-open[[index]]$ready==0L&&open[[index]]$unvalidated==0L&&open[[index]]$blocked+open[[index]]$pending>0L
    open[[index]]$retire_by_owner<-is.na(open[[index]]$retire_replacement)&&rest&&open[[index]]$superseded==0L
  }
  # Erst jetzt loeschen: waehrend der Schleife werden die Kennungen der groesseren
  # Laeufe noch als Vergleichsmenge gebraucht.
  lapply(open,function(group){group$identities<-NULL;group$open_identities<-NULL;group$created<-NULL;group$open_created<-NULL;group})
}
