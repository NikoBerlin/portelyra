data_cash_coverage_editor_error_codes_v1 <- function() c(
  "data_cash_coverage_editor_state_invalid", "data_cash_coverage_editor_context_invalid",
  "data_cash_coverage_editor_catalog_unavailable", "data_cash_coverage_editor_selection_invalid",
  "data_cash_coverage_editor_input_invalid", "data_cash_coverage_editor_preview_required",
  "data_cash_coverage_editor_confirmation_required", "data_cash_coverage_editor_confirmation_consumed",
  "data_cash_coverage_editor_confirmation_expired", "data_cash_coverage_editor_revision_invalid",
  "data_cash_coverage_editor_recovery_required", "data_cash_coverage_editor_recovery_consumed",
  "data_cash_coverage_editor_adapter_failed"
)

.data_cash_coverage_editor_condition <- function(code) {
  if (!is.character(code) || length(code)!=1L || is.na(code) || !code %in% data_cash_coverage_editor_error_codes_v1()) stop("unregistered_data_cash_coverage_editor_error_code", call.=FALSE)
  structure(list(message=code,call=NULL,code=code),class=c("spot_data_cash_coverage_editor_error","error","condition"))
}
.data_cash_coverage_editor_abort <- function(code) stop(.data_cash_coverage_editor_condition(code))
.data_cash_coverage_editor_call <- function(callback,fallback) tryCatch(callback(),
  spot_desktop_product_adapter_domain_error=function(error)stop(error),
  spot_data_cash_coverage_editor_error=function(error)stop(error),
  error=function(error).data_cash_coverage_editor_abort(fallback))

.data_cash_coverage_adapter_names <- function() c(
  "catalog","read_view","revision_candidates","recovery_candidates","preview","reviewed_preview",
  "confirmation","apply","recovery_preview","recovery_confirmation","recovery_apply",
  "check_balance","manual_booking","manual_batch_apply","evidence_overview"
)
.data_cash_coverage_editor_check <- function(editor) {
  required <- c("catalog","read_view","preview","confirmation","apply")
  if (!inherits(editor,"spot_data_cash_coverage_editor_v1") || !is.environment(editor) ||
      !is.environment(editor$previews) || !is.environment(editor$recoveries) ||
      !is.integer(editor$sequence) || length(editor$sequence)!=1L ||
      !is.list(editor$adapter) || !all(required %in% names(editor$adapter)) ||
      any(!names(editor$adapter) %in% .data_cash_coverage_adapter_names()) ||
      !all(vapply(editor$adapter,is.function,logical(1L)))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_state_invalid")
  invisible(TRUE)
}
.data_cash_coverage_editor_context <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context),error=function(error) FALSE)) || !identical(context$runtime_mode,"desktop_product") || !identical(context$role,"desktop_owner")) .data_cash_coverage_editor_abort("data_cash_coverage_editor_context_invalid")
  context
}

new_data_cash_coverage_editor_v1 <- function(adapter) {
  required <- c("catalog","read_view","preview","confirmation","apply")
  if (!is.list(adapter) || !all(required %in% names(adapter)) || any(!names(adapter) %in% .data_cash_coverage_adapter_names()) || !all(vapply(adapter,is.function,logical(1L)))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_state_invalid")
  editor <- new.env(hash=FALSE,parent=emptyenv())
  editor$adapter<-adapter;editor$selection<-NULL
  editor$previews<-new.env(hash=TRUE,parent=emptyenv());editor$recoveries<-new.env(hash=TRUE,parent=emptyenv())
  editor$sequence<-0L;class(editor)<-"spot_data_cash_coverage_editor_v1";editor
}

.data_cash_coverage_label <- function(value) {
  if (!is.character(value)||length(value)!=1L||is.na(value)||!nzchar(value)||value!=trimws(value)||nchar(value,type="bytes")>160L||grepl("[[:cntrl:]]",value)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_catalog_unavailable")
  value
}
.data_cash_coverage_index <- function(rows,prefix,id_field) {
  if (!is.list(rows)||!length(rows)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_catalog_unavailable")
  ids<-vapply(rows,`[[`,character(1L),id_field);if(anyDuplicated(ids)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_catalog_unavailable")
  refs<-sprintf("%s%04d",prefix,seq_along(rows));list(by_ref=setNames(rows,refs),ref_by_id=setNames(refs,ids))
}
.data_cash_coverage_optional_index <- function(rows,id_field) {
  if(!is.list(rows)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_catalog_unavailable")
  if(!length(rows)) return(list(by_ref=list()))
  ids<-vapply(rows,function(row){value<-row[[id_field]];if(!is.character(value)||length(value)!=1L||is.na(value)||!nzchar(value)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_catalog_unavailable");value},character(1L))
  if(anyDuplicated(ids)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_catalog_unavailable")
  list(by_ref=setNames(rows,ids))
}

.data_cash_coverage_adapter_optional <- function(editor,name,context,default) {
  if(!name %in% names(editor$adapter)) return(default)
  .data_cash_coverage_editor_call(function()editor$adapter[[name]](context),"data_cash_coverage_editor_catalog_unavailable")
}

data_cash_coverage_editor_refresh_v1 <- function(editor,context) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  value<-.data_cash_coverage_editor_call(function()editor$adapter$catalog(context),"data_cash_coverage_editor_catalog_unavailable")
  if(!is.list(value)||!identical(value$cash_coverage_catalog_version,1L)||!identical(value$status,"ready")||!is.list(value$portfolios)||!length(value$portfolios)||!is.list(value$accounts)||!length(value$accounts)||!is.list(value$cash_assets)||!length(value$cash_assets)||!identical(value$canonical_ids_exposed,TRUE)||!identical(value$path_exposed,FALSE)||!identical(value$canonical_write,FALSE)||!identical(value$provider_access,FALSE)||!identical(value$network_access,FALSE)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_catalog_unavailable")
  revisions<-.data_cash_coverage_adapter_optional(editor,"revision_candidates",context,list(status="absent",candidates=list()))
  recoveries<-.data_cash_coverage_adapter_optional(editor,"recovery_candidates",context,list(status="absent",candidates=list()))
  if(!is.list(revisions)||!revisions$status%in%c("absent","available")||!is.list(revisions$candidates)||!is.list(recoveries)||!recoveries$status%in%c("absent","available")||!is.list(recoveries$candidates)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_catalog_unavailable")
  portfolios<-.data_cash_coverage_index(value$portfolios,"cash_portfolio_","portfolio_id");accounts<-.data_cash_coverage_index(value$accounts,"cash_account_","account_id");assets<-.data_cash_coverage_index(value$cash_assets,"cash_asset_","asset_id")
  revision_index<-.data_cash_coverage_optional_index(revisions$candidates,"record_ref");recovery_index<-.data_cash_coverage_optional_index(recoveries$candidates,"recovery_ref")
  editor$selection<-list(context_fingerprint=runtime_context_fingerprint(context),portfolios=portfolios,accounts=accounts,assets=assets,revisions=revision_index,recoveries=recovery_index)
  list(cash_coverage_editor_catalog_version=2L,status="ready",
    portfolios=lapply(names(portfolios$by_ref),function(ref){row<-portfolios$by_ref[[ref]];list(ref=ref,label=.data_cash_coverage_label(row$label),currency=row$base_currency)}),
    accounts=lapply(names(accounts$by_ref),function(ref){row<-accounts$by_ref[[ref]];list(ref=ref,label=.data_cash_coverage_label(row$label),portfolio_ref=unname(portfolios$ref_by_id[[row$portfolio_id]]),account_type=row$account_type)}),
    cash_assets=lapply(names(assets$by_ref),function(ref){row<-assets$by_ref[[ref]];list(ref=ref,label=.data_cash_coverage_label(row$label),currency=row$currency)}),
    revision_candidates=revisions$candidates,recovery_candidates=recoveries$candidates,
    canonical_ids_exposed=FALSE,path_exposed=FALSE,internal_ids_exposed=FALSE,fingerprints_exposed=FALSE,
    canonical_write=FALSE,provider_access=FALSE,network_access=FALSE)
}

data_cash_coverage_editor_read_view_v1 <- function(editor,context) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  value<-.data_cash_coverage_editor_call(function()editor$adapter$read_view(context),"data_cash_coverage_editor_catalog_unavailable")
  required<-c("desktop_cash_coverage_read_model_version","status","schema_version","period_count","cash_event_count","income_event_count","reconciliation_count","revision_count","receipt_count","cash_coverage_state","periods","cash_history","income_history","receipt_history","coverage_inferred","canonical_write","asset_activity_write","provider_access","network_access","path_exposed","context_exposed","internal_id_exposed","fingerprint_exposed")
  if(!is.list(value)||!setequal(names(value),required)||!identical(value$desktop_cash_coverage_read_model_version,2L)||!value$status%in%c("absent","available")||!identical(value$cash_coverage_state,"separate_not_read")||identical(value$status,"available")&&!identical(value$schema_version,2901L)||!is.list(value$periods)||!is.list(value$cash_history)||!is.list(value$income_history)||!is.list(value$receipt_history)||any(vapply(value[c("coverage_inferred","canonical_write","asset_activity_write","provider_access","network_access","path_exposed","context_exposed","internal_id_exposed","fingerprint_exposed")],function(item)!identical(item,FALSE),logical(1L)))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_catalog_unavailable")
  value
}

.data_cash_coverage_selection <- function(editor,context) {
  selection<-editor$selection;if(is.null(selection)||!identical(selection$context_fingerprint,runtime_context_fingerprint(context))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_selection_invalid");selection
}
.data_cash_coverage_resolve <- function(selection,area,ref,optional=FALSE) {
  if(optional&&(is.null(ref)||identical(ref,""))) return(NULL)
  if(!is.character(ref)||length(ref)!=1L||is.na(ref)||!nzchar(ref)||is.null(selection[[area]]$by_ref[[ref]])) .data_cash_coverage_editor_abort("data_cash_coverage_editor_selection_invalid")
  selection[[area]]$by_ref[[ref]]
}
.data_cash_coverage_scalar <- function(value,optional=FALSE,allowed=NULL,maximum=80L) {
  if(inherits(value,"Date")) value<-if(length(value)==1L&&!is.na(value)) format(value,"%Y-%m-%d") else ""
  if(optional&&(is.null(value)||identical(value,""))) return(NULL)
  if(!is.character(value)||length(value)!=1L||is.na(value)||value!=trimws(value)||nchar(value,type="bytes")>maximum||grepl("[[:cntrl:]]",value)||!is.null(allowed)&&!value%in%allowed) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  value
}
.data_cash_coverage_request <- function(editor,context,material) {
  editor$sequence<-editor$sequence+1L
  value<-paste("cash-coverage-request-v2",runtime_context_fingerprint(context),editor$sequence,digest::digest(material,algo="sha256"),sep="|")
  paste0("ccrq_",substr(digest::digest(charToRaw(enc2utf8(value)),algo="sha256",serialize=FALSE),1L,32L))
}
.data_cash_coverage_time <- function(value) as.POSIXct(value,format="%Y-%m-%dT%H:%M:%SZ",tz="UTC")
# Die UTC-Zeit folgt aus Tag, Uhrzeit und Zeitzone (#422): Bleibt das Feld leer, rechnet die Karte sie aus, statt sie abtippen zu
# lassen. Eine unbekannte Zeitzone oder Uhrzeit laesst das Feld leer; dann weist die Pruefung es wie bisher ab.
.data_cash_coverage_derived_utc <- function(given,local_date,local_time,zone) {
  if(is.character(given)&&length(given)==1L&&!is.na(given)&&nzchar(trimws(given))) return(given)
  text<-function(value) if(is.character(value)&&length(value)==1L&&!is.na(value)) trimws(value) else ""
  day<-text(local_date);time<-text(local_time);zone<-text(zone)
  if(!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$",day)||!grepl("^[0-9]{2}:[0-9]{2}:[0-9]{2}$",time)||!zone%in%OlsonNames()) return(given)
  moment<-as.POSIXct(paste(day,time),format="%Y-%m-%d %H:%M:%S",tz=zone)
  if(is.na(moment)) given else format(moment,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
}

.data_cash_coverage_regular <- function(action,common,form,related,top=TRUE) {
  action<-.data_cash_coverage_scalar(action,allowed=c("declare_coverage","record_cash_event","record_interest_income","record_reconciliation"))
  base<-c(list(action_type=action),common)
  result<-switch(action,
    declare_coverage={
      mode<-.data_cash_coverage_scalar(form$coverage_mode,allowed=c("not_tracked","income_only","partial","complete_reconciled"));complete<-identical(mode,"complete_reconciled")
      c(base,list(effective_from=.data_cash_coverage_scalar(form$effective_from,maximum=10L),effective_to=.data_cash_coverage_scalar(form$effective_to,TRUE,maximum=10L),coverage_mode=mode,
        opening_balance_decimal=if(complete).data_cash_coverage_scalar(form$amount_decimal) else NULL,
        opening_event_time_evidence=if(complete)"exact_local_zone" else NULL,
        opening_local_time=if(complete).data_cash_coverage_scalar(form$local_time,maximum=8L) else NULL,
        opening_time_zone=if(complete).data_cash_coverage_scalar(form$time_zone,maximum=80L) else NULL,
        opening_effective_at_utc=if(complete).data_cash_coverage_scalar(.data_cash_coverage_derived_utc(form$effective_at_utc,form$effective_from,form$local_time,form$time_zone),maximum=20L) else NULL,
        reconciliation_as_of_date=if(complete).data_cash_coverage_scalar(form$as_of_date,maximum=10L) else NULL,
        observed_balance_decimal=if(complete).data_cash_coverage_scalar(form$observed_balance_decimal) else NULL,
        evidence_fingerprint=if(complete).data_cash_coverage_scalar(form$evidence_fingerprint,maximum=64L) else NULL))
    },
    record_cash_event=c(base,list(event_type=.data_cash_coverage_scalar(form$event_type,allowed=c("opening_balance","deposit","withdrawal","transfer")),related_account_id=if(is.null(related))NULL else related$account_id,event_time_evidence="exact_local_zone",local_date=.data_cash_coverage_scalar(form$local_date,maximum=10L),local_time=.data_cash_coverage_scalar(form$local_time,maximum=8L),time_zone=.data_cash_coverage_scalar(form$time_zone,maximum=80L),effective_at_utc=.data_cash_coverage_scalar(.data_cash_coverage_derived_utc(form$effective_at_utc,form$local_date,form$local_time,form$time_zone),maximum=20L),amount_decimal=.data_cash_coverage_scalar(form$amount_decimal),flow_classification=.data_cash_coverage_scalar(form$flow_classification,allowed=c("not_applicable","unclassified","external_contribution","external_withdrawal","internal_unlinked","investment_settlement","income_receipt","fee_or_tax_payment")))),
    record_interest_income=c(base,list(local_date=.data_cash_coverage_scalar(form$local_date,maximum=10L),gross_income_decimal=.data_cash_coverage_scalar(form$gross_income_decimal),linked_cash_event_ref=.data_cash_coverage_scalar(form$linked_cash_event_ref,TRUE))),
    record_reconciliation=c(base,list(as_of_date=.data_cash_coverage_scalar(form$as_of_date,maximum=10L),observed_balance_decimal=.data_cash_coverage_scalar(form$observed_balance_decimal),evidence_fingerprint=.data_cash_coverage_scalar(form$evidence_fingerprint,maximum=64L))))
  result
}

# Welche Formularfelder der Kern bei dieser Aktion tatsaechlich liest. Die
# Oberflaeche zeigte bisher alle zwanzig Felder immer; bei
# "Coverage-Zeitraum erklaeren" blieben sechs davon ohne jede Wirkung, und das sah
# aus, als sei die Eingabe falsch - sie war wirkungslos (#422). Die Liste gehoert hierher, neben .data_cash_coverage_regular,
# damit beide nicht auseinanderlaufen; ein Vertragstest vergleicht sie.
data_cash_coverage_editor_relevant_fields_v1 <- function(action,coverage_mode=NULL) {
  gemeinsam<-c("action_type","portfolio_ref","account_ref","cash_asset_ref")
  if(identical(action,"void"))return(c("action_type","revision_predecessor_refs"))
  if(action%in%c("correct","supersede")){
    # Welche Ersatzaktionen gelten, entscheiden die gewaehlten Vorgaenger; bis sie
    # gewaehlt sind, ist jedes Feld moeglich.
    return(unique(c("action_type","revision_predecessor_refs",gemeinsam,
      unlist(lapply(c("declare_coverage","record_cash_event","record_interest_income","record_reconciliation"),
        function(item)data_cash_coverage_editor_relevant_fields_v1(item,"complete_reconciled")),use.names=FALSE))))
  }
  switch(action,
    declare_coverage=c(gemeinsam,"coverage_mode","effective_from","effective_to",
      # Nur eine vollstaendig abgestimmte Erklaerung traegt Eroeffnungssaldo und
      # Abstimmung mit sich; sonst bleiben diese sieben Felder ungelesen.
      if(identical(coverage_mode,"complete_reconciled"))c("amount_decimal","local_time","time_zone","effective_at_utc","as_of_date","observed_balance_decimal","evidence_fingerprint")else character()),
    record_cash_event=c(gemeinsam,"event_type","related_account_ref","local_date","local_time","time_zone","effective_at_utc","amount_decimal","flow_classification"),
    record_interest_income=c(gemeinsam,"local_date","gross_income_decimal","linked_cash_event_ref"),
    record_reconciliation=c(gemeinsam,"as_of_date","observed_balance_decimal","evidence_fingerprint"),
    character())
}

.data_cash_coverage_store_preview <- function(editor,context,command,value,now_utc) {
  action<-command$action_type
  if(!is.list(value)||!identical(value$desktop_cash_coverage_preview_version,2L)||!identical(value$status,"ready_for_confirmation")||!identical(value$action_type,action)||!isTRUE(value$confirmation_required)||!isTRUE(value$one_attempt_only)||any(vapply(value[c("canonical_write","asset_activity_write","provider_access","network_access","private_data_access")],function(item)!identical(item,FALSE),logical(1L)))||!is.list(value$projection)||!is.list(value$projection_before)||!is.list(value$reconciliation)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_adapter_failed")
  preview_ref<-sprintf("cash_preview_%04d",editor$sequence);expires<-format(.data_cash_coverage_time(now_utc)+600,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
  public<-list(cash_coverage_editor_preview_version=2L,status="pending_confirmation",preview_ref=preview_ref,action_type=action,operation_type=value$operation_type,input_mode=value$input_mode,projection_before=value$projection_before,projection=value$projection,reconciliation=value$reconciliation,confirmation_required=TRUE,one_attempt_only=TRUE,canonical_write=FALSE,asset_activity_write=FALSE,provider_access=FALSE,network_access=FALSE,canonical_ids_exposed=FALSE,path_exposed=FALSE,fingerprint_exposed=FALSE,expires_at_utc=expires)
  assign(preview_ref,list(context_fingerprint=runtime_context_fingerprint(context),command=command,server_preview=value,expires_at_utc=expires,confirmed=FALSE,consumed=FALSE,public=public),envir=editor$previews);public
}

data_cash_coverage_editor_prepare_v1 <- function(editor,context,form,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  required<-c("action_type","portfolio_ref","account_ref","cash_asset_ref","related_account_ref","coverage_mode","effective_from","effective_to","event_type","local_date","local_time","time_zone","effective_at_utc","amount_decimal","flow_classification","gross_income_decimal","linked_cash_event_ref","as_of_date","observed_balance_decimal","evidence_fingerprint","revision_predecessor_refs")
  if(!is.list(form)||!setequal(names(form),required)||!is.character(now_utc)||length(now_utc)!=1L||is.na(.data_cash_coverage_time(now_utc))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  selection<-.data_cash_coverage_selection(editor,context);portfolio<-.data_cash_coverage_resolve(selection,"portfolios",form$portfolio_ref);account<-.data_cash_coverage_resolve(selection,"accounts",form$account_ref);asset<-.data_cash_coverage_resolve(selection,"assets",form$cash_asset_ref);related<-.data_cash_coverage_resolve(selection,"accounts",form$related_account_ref,TRUE)
  if(!identical(account$portfolio_id,portfolio$portfolio_id)||!is.null(related)&&!identical(related$portfolio_id,portfolio$portfolio_id)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_selection_invalid")
  action<-.data_cash_coverage_scalar(form$action_type,allowed=c("declare_coverage","record_cash_event","record_interest_income","record_reconciliation","correct","supersede","void"))
  request_ref<-.data_cash_coverage_request(editor,context,form)
  scope<-list(portfolio_id=portfolio$portfolio_id,account_id=account$account_id,cash_asset_id=asset$asset_id)
  if(action%in%c("correct","supersede","void")){
    refs<-form$revision_predecessor_refs
    if(!is.character(refs)||!length(refs)||anyNA(refs)||any(!nzchar(refs))||anyDuplicated(refs)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_revision_invalid")
    candidates<-lapply(refs,function(ref).data_cash_coverage_resolve(selection,"revisions",ref))
    replacements<-list()
    if(!identical(action,"void")){
      actions<-unlist(lapply(candidates,`[[`,"replacement_action_types"),use.names=FALSE)
      if(!length(actions)||anyDuplicated(actions)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_revision_invalid")
      replacements<-lapply(actions,function(item).data_cash_coverage_regular(item,scope,form,related,FALSE))
    }
    command<-list(action_type=action,request_ref=request_ref,input_mode="manual_entry",source_candidate_fingerprint=NULL,predecessor_refs=as.list(unname(refs)),replacements=replacements)
  } else {
    common<-c(list(request_ref=request_ref,input_mode="manual_entry",source_candidate_fingerprint=NULL),scope)
    command<-.data_cash_coverage_regular(action,common,form,related,TRUE)
  }
  value<-.data_cash_coverage_editor_call(function()editor$adapter$preview(context,command),"data_cash_coverage_editor_adapter_failed")
  .data_cash_coverage_store_preview(editor,context,command,value,now_utc)
}

data_cash_coverage_editor_prepare_reviewed_v1 <- function(editor,context,reviewed_candidate,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  if(!"reviewed_preview"%in%names(editor$adapter)||!is.list(reviewed_candidate)||!is.character(now_utc)||length(now_utc)!=1L||is.na(.data_cash_coverage_time(now_utc))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  request_ref<-.data_cash_coverage_request(editor,context,reviewed_candidate)
  value<-.data_cash_coverage_editor_call(function()editor$adapter$reviewed_preview(context,reviewed_candidate,request_ref),"data_cash_coverage_editor_adapter_failed")
  .data_cash_coverage_store_preview(editor,context,value$command,value,now_utc)
}

data_cash_coverage_editor_confirm_v1 <- function(editor,context,preview_ref,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  if(!is.character(preview_ref)||length(preview_ref)!=1L||!exists(preview_ref,envir=editor$previews,inherits=FALSE)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_preview_required")
  state<-get(preview_ref,envir=editor$previews,inherits=FALSE);if(isTRUE(state$consumed)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_confirmation_consumed")
  # Die Vorschau einer einfachen Buchung traegt einen Stapel, kein Einzelkommando;
  # sie wird ueber ihren eigenen Weg bestaetigt und geschrieben. Bewusst
  # [["command"]]: `$command` ergaenzt den Namen und faende den Stapel `commands`.
  if(is.null(state[["command"]])) .data_cash_coverage_editor_abort("data_cash_coverage_editor_preview_required")
  if(!identical(state$context_fingerprint,runtime_context_fingerprint(context))||is.na(.data_cash_coverage_time(now_utc))||.data_cash_coverage_time(now_utc)>.data_cash_coverage_time(state$expires_at_utc)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_confirmation_expired")
  challenge<-paste0("cccf_",substr(digest::digest(charToRaw(enc2utf8(paste(preview_ref,state$server_preview$preview_fingerprint,sep="|"))),algo="sha256",serialize=FALSE),1L,32L))
  authority<-.data_cash_coverage_editor_call(function()editor$adapter$confirmation(context,state$server_preview,challenge,now_utc,state$expires_at_utc),"data_cash_coverage_editor_adapter_failed");state$authority<-authority;state$confirmed<-TRUE;assign(preview_ref,state,envir=editor$previews)
  list(confirmation_version=1L,preview_ref=preview_ref,status="confirmed",one_use=TRUE)
}

data_cash_coverage_editor_execute_v1 <- function(editor,context,preview_ref,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  if(!is.character(preview_ref)||length(preview_ref)!=1L||!exists(preview_ref,envir=editor$previews,inherits=FALSE)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_preview_required")
  state<-get(preview_ref,envir=editor$previews,inherits=FALSE);if(isTRUE(state$consumed)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_confirmation_consumed")
  if(is.null(state[["command"]])) .data_cash_coverage_editor_abort("data_cash_coverage_editor_preview_required")
  if(!isTRUE(state$confirmed)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_confirmation_required")
  if(is.na(.data_cash_coverage_time(now_utc))||.data_cash_coverage_time(now_utc)>.data_cash_coverage_time(state$expires_at_utc)||!identical(state$context_fingerprint,runtime_context_fingerprint(context))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_confirmation_expired")
  state$consumed<-TRUE;state$confirmed<-FALSE;assign(preview_ref,state,envir=editor$previews)
  result<-.data_cash_coverage_editor_call(function()editor$adapter$apply(context,state$command,state$authority,now_utc),"data_cash_coverage_editor_adapter_failed")
  required<-c("status","action_type","operation_type","command_ref","receipt_ref","schema_version","period_count","cash_event_count","income_event_count","reconciliation_count","revision_count","predecessor_preserved","input_mode","canonical_write","asset_activity_write","provider_access","network_access")
  if(!is.list(result)||!setequal(names(result),required)||!result$status%in%c("committed","already_committed")||!identical(result$schema_version,2901L)||!identical(result$predecessor_preserved,TRUE)||!identical(result$canonical_write,FALSE)||!identical(result$asset_activity_write,FALSE)||!identical(result$provider_access,FALSE)||!identical(result$network_access,FALSE)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_adapter_failed")
  result
}

data_cash_coverage_editor_prepare_recovery_v1 <- function(editor,context,recovery_ref,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  if(!all(c("recovery_preview","recovery_confirmation","recovery_apply")%in%names(editor$adapter))||!is.character(now_utc)||length(now_utc)!=1L||is.na(.data_cash_coverage_time(now_utc))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_recovery_required")
  selection<-.data_cash_coverage_selection(editor,context);.data_cash_coverage_resolve(selection,"recoveries",recovery_ref)
  value<-.data_cash_coverage_editor_call(function()editor$adapter$recovery_preview(context,recovery_ref),"data_cash_coverage_editor_adapter_failed")
  if(!is.list(value)||!is.list(value$public_preview)||!is.list(value$trusted_preview)||!identical(value$public_preview$status,"ready_for_recovery_confirmation")||!identical(value$trusted_preview$status,"ready_for_recovery_confirmation")||!identical(value$public_preview$recovery_confirmation_required,TRUE)||!identical(value$public_preview$automatic_retry,FALSE)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_adapter_failed")
  editor$sequence<-editor$sequence+1L;preview_ref<-sprintf("cash_recovery_preview_%04d",editor$sequence);expires<-format(.data_cash_coverage_time(now_utc)+600,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
  public<-list(cash_coverage_editor_recovery_preview_version=1L,status=value$public_preview$status,preview_ref=preview_ref,recovery_ref=value$public_preview$recovery_ref,action_type=value$public_preview$action_type,operation_type=value$public_preview$operation_type,input_mode=value$public_preview$input_mode,before=value$public_preview$before,after=value$public_preview$after,recovery_reason=value$public_preview$recovery_reason,confirmation_required=TRUE,automatic_retry=FALSE,canonical_write=FALSE,asset_activity_write=FALSE,provider_access=FALSE,network_access=FALSE,path_exposed=FALSE,internal_id_exposed=FALSE,fingerprint_exposed=FALSE,expires_at_utc=expires)
  assign(preview_ref,list(context_fingerprint=runtime_context_fingerprint(context),trusted=value$trusted_preview,expires_at_utc=expires,confirmed=FALSE,consumed=FALSE,public=public),envir=editor$recoveries);public
}

data_cash_coverage_editor_confirm_recovery_v1 <- function(editor,context,preview_ref,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  if(!is.character(preview_ref)||length(preview_ref)!=1L||!exists(preview_ref,envir=editor$recoveries,inherits=FALSE)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_recovery_required")
  state<-get(preview_ref,envir=editor$recoveries,inherits=FALSE);if(isTRUE(state$consumed)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_recovery_consumed")
  if(!identical(state$context_fingerprint,runtime_context_fingerprint(context))||is.na(.data_cash_coverage_time(now_utc))||.data_cash_coverage_time(now_utc)>.data_cash_coverage_time(state$expires_at_utc)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_confirmation_expired")
  challenge<-paste0("ccrc_",substr(digest::digest(charToRaw(enc2utf8(paste(preview_ref,state$trusted$recovery_plan_fingerprint,sep="|"))),algo="sha256",serialize=FALSE),1L,32L))
  state$authority<-.data_cash_coverage_editor_call(function()editor$adapter$recovery_confirmation(context,state$trusted,challenge,now_utc,state$expires_at_utc),"data_cash_coverage_editor_adapter_failed");state$confirmed<-TRUE;assign(preview_ref,state,envir=editor$recoveries)
  list(confirmation_version=1L,preview_ref=preview_ref,status="recovery_confirmed",one_use=TRUE)
}

data_cash_coverage_editor_execute_recovery_v1 <- function(editor,context,preview_ref,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  if(!is.character(preview_ref)||length(preview_ref)!=1L||!exists(preview_ref,envir=editor$recoveries,inherits=FALSE)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_recovery_required")
  state<-get(preview_ref,envir=editor$recoveries,inherits=FALSE);if(isTRUE(state$consumed)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_recovery_consumed");if(!isTRUE(state$confirmed)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_confirmation_required")
  state$consumed<-TRUE;state$confirmed<-FALSE;assign(preview_ref,state,envir=editor$recoveries)
  result<-.data_cash_coverage_editor_call(function()editor$adapter$recovery_apply(context,state$trusted,state$authority,now_utc),"data_cash_coverage_editor_adapter_failed")
  if(!is.list(result)||!result$status%in%c("recovered_committed","already_committed")||!identical(result$schema_version,2901L)||!identical(result$predecessor_preserved,TRUE)||!identical(result$canonical_write,FALSE)||!identical(result$asset_activity_write,FALSE)||!identical(result$provider_access,FALSE)||!identical(result$network_access,FALSE)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_adapter_failed")
  result
}

# --- Einfache Handbuchung und nachtraeglicher Pruef-Saldo (#417, #419) --------
#
# Eine Cash-Transaktion soll sich unkompliziert manuell eingeben lassen. Der Weg ueber die zwanzig Felder des
# Editors bleibt fuer Sonderfaelle; diese beiden Vorgaenge brauchen Konto, Datum
# und Betrag. Die Kommandos bildet der Kern, bestaetigt und geschrieben wird
# ueber denselben Weg wie jedes andere Cash-Kommando.

.data_cash_coverage_simple_scope <- function(editor,context,form) {
  selection<-.data_cash_coverage_selection(editor,context)
  account<-.data_cash_coverage_resolve(selection,"accounts",form$account_ref)
  # Gibt es genau ein Cash-Asset, ist es keine Frage an den Eigentuemer.
  asset_ref<-form$cash_asset_ref
  if((is.null(asset_ref)||identical(asset_ref,""))&&length(selection$assets$by_ref)==1L) asset_ref<-names(selection$assets$by_ref)[[1L]]
  asset<-.data_cash_coverage_resolve(selection,"assets",asset_ref)
  list(portfolio_id=account$portfolio_id,account_id=account$account_id,cash_asset_id=asset$asset_id)
}
.data_cash_coverage_flags_clear <- function(value) all(vapply(c("canonical_write","asset_activity_write","provider_access","network_access","path_exposed"),function(name)identical(value[[name]],FALSE),logical(1L)))

# SHA-256 einer gewaehlten Belegdatei. Die App bildet ihn selbst, wie beim
# Statement-Import; niemand tippt 64 Zeichen ab.
data_cash_coverage_evidence_file_fingerprint_v1 <- function(path) {
  if(!is.character(path)||length(path)!=1L||is.na(path)||!nzchar(path)||!file.exists(path)||dir.exists(path)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  value<-digest::digest(file=path,algo="sha256")
  if(!is.character(value)||!grepl("^[a-f0-9]{64}$",value)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  value
}

data_cash_coverage_editor_prepare_check_balance_v1 <- function(editor,context,form,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  required<-c("account_ref","cash_asset_ref","as_of_date","observed_balance_decimal","evidence_kind","evidence_fingerprint")
  if(!"check_balance"%in%names(editor$adapter)||!is.list(form)||!setequal(names(form),required)||!is.character(now_utc)||length(now_utc)!=1L||is.na(.data_cash_coverage_time(now_utc))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  scope<-.data_cash_coverage_simple_scope(editor,context,form)
  kind<-.data_cash_coverage_scalar(form$evidence_kind,allowed=c("document","owner_sighted","owner_asserted_without_balance"))
  asserted<-identical(kind,"owner_asserted_without_balance")
  request<-c(list(request_ref=.data_cash_coverage_request(editor,context,form)),scope,list(
    as_of_date=.data_cash_coverage_scalar(form$as_of_date,maximum=10L),
    # Ohne Saldopruefung gibt es keinen beobachteten Saldo; der Kern nimmt den errechneten.
    observed_balance_decimal=if(asserted)NULL else .data_cash_coverage_scalar(form$observed_balance_decimal),
    evidence_kind=kind,
    evidence_fingerprint=if(identical(kind,"document")).data_cash_coverage_scalar(form$evidence_fingerprint,maximum=64L) else NULL))
  value<-.data_cash_coverage_editor_call(function()editor$adapter$check_balance(context,request),"data_cash_coverage_editor_adapter_failed")
  if(!is.list(value)||!identical(value$desktop_cash_check_balance_version,1L)||!is.list(value$explanation)||!.data_cash_coverage_flags_clear(value)||
     !value$status%in%c("ready_for_confirmation","balance_mismatch","closed_period_reconciles_at_end")) .data_cash_coverage_editor_abort("data_cash_coverage_editor_adapter_failed")
  if(!identical(value$status,"ready_for_confirmation")) return(list(cash_check_balance_version=1L,status=value$status,preview_ref=NULL,explanation=value$explanation))
  public<-.data_cash_coverage_store_preview(editor,context,value$command,value$preview,now_utc)
  # Nur Erklaerung und Vorschau-Ref gehen nach aussen. Die Projektion des Kerns
  # traegt Konto-IDs und bleibt im Editor.
  list(cash_check_balance_version=1L,status="pending_confirmation",preview_ref=public$preview_ref,explanation=value$explanation)
}

data_cash_coverage_editor_prepare_booking_v1 <- function(editor,context,form,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  required<-c("account_ref","cash_asset_ref","local_date","kind","amount_decimal")
  if(!all(c("manual_booking","manual_batch_apply")%in%names(editor$adapter))||!is.list(form)||!setequal(names(form),required)||!is.character(now_utc)||length(now_utc)!=1L||is.na(.data_cash_coverage_time(now_utc))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  scope<-.data_cash_coverage_simple_scope(editor,context,form)
  request<-c(list(request_ref=.data_cash_coverage_request(editor,context,form)),scope,list(
    local_date=.data_cash_coverage_scalar(form$local_date,maximum=10L),
    kind=.data_cash_coverage_scalar(form$kind,allowed=c("deposit","withdrawal","interest")),
    amount_decimal=.data_cash_coverage_scalar(form$amount_decimal)))
  value<-.data_cash_coverage_editor_call(function()editor$adapter$manual_booking(context,request),"data_cash_coverage_editor_adapter_failed")
  if(!is.list(value)||!identical(value$desktop_cash_manual_booking_version,1L)||!is.list(value$explanation)||!.data_cash_coverage_flags_clear(value)||
     !value$status%in%c("ready_for_confirmation","outside_coverage","coverage_mode_excludes_cash_events","before_reconciled_state")) .data_cash_coverage_editor_abort("data_cash_coverage_editor_adapter_failed")
  if(!identical(value$status,"ready_for_confirmation")) return(list(cash_booking_version=1L,status=value$status,preview_ref=NULL,explanation=value$explanation))
  preview<-value$preview
  if(!is.list(value$commands)||!length(value$commands)||!is.list(preview)||!identical(preview$status,"ready_for_confirmation")||!is.character(preview$preview_fingerprint)||!identical(nchar(preview$preview_fingerprint),64L)||!identical(preview$canonical_write,FALSE)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_adapter_failed")
  preview_ref<-sprintf("cash_booking_preview_%04d",editor$sequence);expires<-format(.data_cash_coverage_time(now_utc)+600,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
  assign(preview_ref,list(context_fingerprint=runtime_context_fingerprint(context),commands=value$commands,preview_fingerprint=preview$preview_fingerprint,expires_at_utc=expires,confirmed=FALSE,consumed=FALSE,confirmed_at_utc=NULL),envir=editor$previews)
  list(cash_booking_version=1L,status="pending_confirmation",preview_ref=preview_ref,explanation=value$explanation,
    command_count=length(value$commands))
}

.data_cash_coverage_booking_state <- function(editor,context,preview_ref,now_utc) {
  if(!is.character(preview_ref)||length(preview_ref)!=1L||!grepl("^cash_booking_preview_",preview_ref)||!exists(preview_ref,envir=editor$previews,inherits=FALSE)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_preview_required")
  state<-get(preview_ref,envir=editor$previews,inherits=FALSE)
  if(isTRUE(state$consumed)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_confirmation_consumed")
  if(!identical(state$context_fingerprint,runtime_context_fingerprint(context))||!is.character(now_utc)||length(now_utc)!=1L||is.na(.data_cash_coverage_time(now_utc))||.data_cash_coverage_time(now_utc)>.data_cash_coverage_time(state$expires_at_utc)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_confirmation_expired")
  state
}

data_cash_coverage_editor_confirm_booking_v1 <- function(editor,context,preview_ref,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  state<-.data_cash_coverage_booking_state(editor,context,preview_ref,now_utc)
  state$confirmed<-TRUE;state$confirmed_at_utc<-now_utc;assign(preview_ref,state,envir=editor$previews)
  list(confirmation_version=1L,preview_ref=preview_ref,status="confirmed",one_use=TRUE)
}

data_cash_coverage_editor_execute_booking_v1 <- function(editor,context,preview_ref,now_utc) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  state<-.data_cash_coverage_booking_state(editor,context,preview_ref,now_utc)
  if(!isTRUE(state$confirmed)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_confirmation_required")
  # Verbraucht vor dem Versuch: ein zweiter Klick startet keinen zweiten Vorgang.
  state$consumed<-TRUE;state$confirmed<-FALSE;assign(preview_ref,state,envir=editor$previews)
  result<-.data_cash_coverage_editor_call(function()editor$adapter$manual_batch_apply(context,state$commands,state$preview_fingerprint,state$confirmed_at_utc,now_utc),"data_cash_coverage_editor_adapter_failed")
  if(!is.list(result)||!identical(result$desktop_cash_coverage_batch_version,1L)||!result$status%in%c("committed","already_committed")) .data_cash_coverage_editor_abort("data_cash_coverage_editor_adapter_failed")
  result
}

data_cash_coverage_editor_evidence_overview_v1 <- function(editor,context,as_of_date) {
  .data_cash_coverage_editor_check(editor);.data_cash_coverage_editor_context(context)
  day<-.data_cash_coverage_scalar(as_of_date,maximum=10L)
  if(!"evidence_overview"%in%names(editor$adapter)||!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$",day)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  value<-.data_cash_coverage_editor_call(function()editor$adapter$evidence_overview(context,day),"data_cash_coverage_editor_adapter_failed")
  if(!is.list(value)||!identical(value$desktop_cash_evidence_overview_version,1L)||!value$status%in%c("absent","available")||!is.list(value$accounts)||!identical(value$internal_id_exposed,FALSE)||!.data_cash_coverage_flags_clear(value)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_adapter_failed")
  value
}

.data_cash_coverage_datum <- function(value) {
  if(is.null(value)||!is.character(value)||length(value)!=1L||is.na(value)) return("—")
  formatted<-tryCatch(format(as.Date(value),"%d.%m.%Y"),error=function(error)NA_character_)
  if(is.na(formatted)) value else formatted
}
.data_cash_coverage_betrag <- function(value) if(is.null(value)) "—" else gsub(".",",",as.character(value),fixed=TRUE)

# "Bis hier belegt" und "danach unveraendert angenommen" sind zwei Aussagen. Eine
# Abdeckung laeuft nach vorn offen weiter, auch wenn der letzte Nachweis Monate
# alt ist; diese Tabelle sagt, womit und bis wann der Saldo belegt ist (#417).
data_cash_coverage_evidence_frame_v1 <- function(value) {
  if(!is.list(value)||!is.list(value$accounts)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  rows<-value$accounts
  if(!length(rows)) return(data.frame(Hinweis="Noch kein Cash-Konto mit Abdeckung.",stringsAsFactors=FALSE))
  nachweis<-c(document="Beleg oder Auszug",owner_sighted="vom Eigentümer gesichtet",owner_asserted_without_balance="ohne Saldoprüfung erklärt")
  # Anfangssaldo mit Herkunft und ab wann abgeglichen (#529, Festlegung 31.10.2026); Betraege mit Einheit (#529 Punkt 8).
  herkunft<-c(statement="aus Auszug belegt",check_balance="aus Prüf-Saldo abgeleitet",assumed="angenommen, ohne Saldo",manual="eigene Angabe")
  waehrung<-function(row){unit<-as.character(if(is.null(row$cash_asset_label))"" else row$cash_asset_label);if(grepl("^[A-Z]{3}$",unit))unit else ""}
  anfang<-function(row){if(is.null(row$opening_balance_decimal))return("—")
    origin<-if(is.null(row$opening_origin))"" else as.character(row$opening_origin)
    paste0(pl_amount_v1(row$opening_balance_decimal,waehrung(row),2L,"—"),if(origin%in%names(herkunft))paste0(" · ",herkunft[[origin]]) else "")}
  data.frame(
    Konto=vapply(rows,function(row)as.character(row$account_label),character(1L)),
    `Abgeglichen ab`=vapply(rows,function(row).data_cash_coverage_datum(row$reconciled_from_date),character(1L)),
    Anfangssaldo=vapply(rows,anfang,character(1L)),
    Stand=vapply(rows,function(row)if(is.null(row$proven_through_date))"nicht abgestimmt" else if(identical(row$evidence_kind,"owner_asserted_without_balance"))"erklärt, ungeprüft" else "abgestimmt",character(1L)),
    `Belegt bis`=vapply(rows,function(row).data_cash_coverage_datum(row$proven_through_date),character(1L)),
    Saldo=vapply(rows,function(row)pl_amount_v1(row$proven_balance_decimal,waehrung(row),2L,"—"),character(1L)),
    Nachweis=vapply(rows,function(row)if(is.null(row$evidence_kind))"—" else unname(nachweis[[row$evidence_kind]]),character(1L)),
    `Letzte Bewegung`=vapply(rows,function(row).data_cash_coverage_datum(row$latest_movement_date),character(1L)),
    `Seither angenommen`=vapply(rows,function(row)if(is.null(row$proven_through_date))"—" else if(as.integer(row$movement_after_proof_count)>0L)sprintf("%d Bewegungen ohne Abstimmung",as.integer(row$movement_after_proof_count)) else sprintf("%d Tage, keine Bewegung",as.integer(row$proof_age_days)),character(1L)),
    check.names=FALSE,stringsAsFactors=FALSE)
}

# Was der Pruef-Saldo aendern wuerde, in Worten. Der Eroeffnungssaldo steht
# ausdruecklich da: Er ergibt sich aus Pruef-Saldo minus gebuchter Bewegungen, und
# an ihm ist abzulesen, ob die Buchungen bei null beginnen.
data_cash_check_balance_message_v1 <- function(prepared) {
  if(!is.list(prepared)||!is.list(prepared$explanation)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  e<-prepared$explanation;tag<-.data_cash_coverage_datum(e$as_of_date);b<-.data_cash_coverage_betrag
  if(identical(prepared$status,"balance_mismatch")) return(list(tone="error",title=paste("Saldo stimmt nicht · Differenz",b(e$difference_decimal)),
    copy=paste0("Gebucht ergibt zum ",tag," ",b(e$computed_balance_decimal),", beobachtet sind ",b(e$observed_balance_decimal),". Nichts wird geschrieben; die Abweichung liegt in den Buchungen bis zu diesem Tag.")))
  if(identical(prepared$status,"closed_period_reconciles_at_end")) return(list(tone="warning",title="Geschlossener Zeitraum wird an seinem Ende abgestimmt",
    copy=paste("Als Abstimmungsdatum gilt hier",.data_cash_coverage_datum(e$required_as_of_date),"– das Ende des Zeitraums.")))
  ungeprueft<-!isTRUE(e$balance_checked)
  herkunft<-switch(as.character(e$opening_balance_origin),
    derived_from_check_balance="ergibt sich aus Prüf-Saldo minus gebuchter Bewegungen",
    existing_opening="bereits gebucht",assumed_zero="angenommen, weil kein Saldo vorliegt","")
  if(identical(e$operation,"raise_partial_to_reconciled")) list(
    tone="warning",
    title=if(ungeprueft)paste("Abdeckung ohne Saldoprüfung als vollständig erklären · Stand",tag) else paste("Abdeckung auf abgestimmt heben · Stand",tag),
    copy=paste0("Eröffnungssaldo ",b(e$opening_balance_decimal)," (",herkunft,") · ",e$cash_event_count," Bewegungen ergeben ",b(e$movement_delta_decimal)," · Saldo ",b(e$observed_balance_decimal),".",
      if(ungeprueft)" Geprüft wird dabei nichts: Der gespeicherte Saldo ist der errechnete, und die Übersicht weist das Konto als „erklärt, ungeprüft“ aus." else " Der bisherige Zeitraum bleibt als ersetzter Stand erhalten."))
  else list(tone="neutral",title=paste("Weitere Abstimmung · Stand",tag),
    copy=paste0("Errechnet ",b(e$computed_balance_decimal)," = beobachtet ",b(e$observed_balance_decimal),if(ungeprueft)" · ohne Saldoprüfung erklärt." else "."))
}

data_cash_booking_message_v1 <- function(prepared) {
  if(!is.list(prepared)||!is.list(prepared$explanation)) .data_cash_coverage_editor_abort("data_cash_coverage_editor_input_invalid")
  e<-prepared$explanation;tag<-.data_cash_coverage_datum(e$local_date)
  art<-c(deposit="Zugang",withdrawal="Abgang",interest="Zinsgutschrift")
  if(identical(prepared$status,"before_reconciled_state")) return(list(tone="warning",title=paste("Das Konto ist bis",.data_cash_coverage_datum(e$reconciled_through),"abgestimmt"),
    copy="Die Buchung liegt am oder vor diesem Tag und würde einen geprüften Saldo verändern. Das ist eine Korrektur der Historie und läuft über „Erweitert“; nichts wird geschrieben."))
  if(identical(prepared$status,"outside_coverage")) return(list(tone="warning",title="Der Tag liegt außerhalb der Abdeckung dieses Kontos",
    copy=paste("Abgedeckt ist das Konto ab",.data_cash_coverage_datum(e$covered_from),"– der Zeitraum wird nicht stillschweigend verlängert.")))
  if(identical(prepared$status,"coverage_mode_excludes_cash_events")) return(list(tone="warning",title="Dieses Konto führt keine Cash-Bewegungen",
    copy="Der Abdeckungsmodus des Kontos lässt nur Erträge oder gar nichts zu."))
  list(tone="warning",title=paste(unname(art[[as.character(e$kind)]]),.data_cash_coverage_betrag(e$amount_decimal),"am",tag),
    copy=paste0(if(isTRUE(e$declares_coverage))"Das Konto hat noch keinen Abdeckungszeitraum; er wird ab diesem Tag als Teilabdeckung angelegt. " else "",
      if(identical(e$kind,"interest"))"Gebucht werden Cash-Zugang und Zinsertrag zusammen. " else "",
      "Ein Vorgang, eine Bestätigung."))
}
