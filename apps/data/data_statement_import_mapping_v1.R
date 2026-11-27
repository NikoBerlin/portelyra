data_statement_import_mapping_error_codes_v1 <- function() c(
  "data_statement_import_mapping_input_invalid",
  "data_statement_import_mapping_boundary_failed",
  "statement_import_mapping_input_invalid",
  "statement_import_mapping_decimal_invalid",
  "statement_import_mapping_valuation_invalid",
  "statement_import_mapping_duplicate_invalid",
  "statement_import_mapping_authority_invalid",
  "statement_import_mapping_quantity_invalid",
  "statement_import_mapping_timezone_invalid",
  "statement_mapping_profile_input_invalid",
  "statement_mapping_profile_context_invalid",
  "statement_mapping_profile_storage_invalid",
  "statement_mapping_profile_duplicate_invalid",
  "statement_mapping_profile_target_invalid",
  "statement_mapping_profile_ref_invalid",
  "statement_mapping_profile_revision_conflict",
  "statement_mapping_profile_adapter_mismatch",
  "statement_mapping_profile_not_found",
  "statement_exchange_adapter_header_invalid",
  "statement_exchange_adapter_overlay_invalid",
  "statement_exchange_adapter_period_invalid",
  "statement_exchange_adapter_profile_invalid",
  "statement_exchange_adapter_source_invalid",
  "statement_exchange_adapter_timezone_invalid"
)

.data_statement_import_mapping_abort <- function(code) {
  if(!is.character(code)||length(code)!=1L||is.na(code)||!code%in%data_statement_import_mapping_error_codes_v1())code<-"data_statement_import_mapping_boundary_failed"
  stop(structure(list(message=code,call=NULL,code=code),class=c("spot_data_statement_import_mapping_error","error","condition")))
}

.data_statement_import_mapping_text <- function(value) is.character(value)&&length(value)==1L&&!is.na(value)&&nzchar(value)&&value==trimws(value)&&nchar(value,type="bytes")<=200L&&!grepl("[[:cntrl:]]",value)

# Pfade sind keine Anzeigetexte: Dateien aus der Ablage liegen tief im Datenraum (Datenraum, Pruefwert als Name) und sind laenger als
# 200 Byte. Bis rc.343 galt hier die Textgrenze, und jede Datei aus der Ablage wurde als ungueltig abgewiesen.
.data_statement_import_mapping_path <- function(value) is.character(value)&&length(value)==1L&&!is.na(value)&&nzchar(value)&&value==trimws(value)&&nchar(value,type="bytes")<=4096L&&!grepl("[[:cntrl:]]",value)

.data_statement_import_mapping_run <- function(project_root,payload) {
  python<-Sys.which("python3");cli<-file.path(project_root,"scripts","statement_import_mapping.py")
  if(!nzchar(python)||!file.exists(cli)||dir.exists(cli)||nzchar(Sys.readlink(cli))) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  encoded<-as.character(jsonlite::toJSON(payload,auto_unbox=TRUE,null="null",na="null",digits=NA,pretty=FALSE))
  temporary<-tempfile("portelyra-statement-mapping-");if(!dir.create(temporary,mode="0700")) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  on.exit(unlink(temporary,recursive=TRUE,force=TRUE),add=TRUE)
  stdout<-file.path(temporary,"stdout.json");stderr<-file.path(temporary,"stderr.txt");file.create(stdout);file.create(stderr);Sys.chmod(c(stdout,stderr),"0600",use_umask=FALSE)
  status<-tryCatch(suppressWarnings(system2(python,c("-B","-E","-s",shQuote(cli)),input=encoded,stdout=stdout,stderr=stderr,wait=TRUE)),error=function(error)NA_integer_)
  raw_out<-readBin(stdout,"raw",n=32000001L);raw_err<-readBin(stderr,"raw",n=32000001L)
  parsed<-tryCatch(jsonlite::fromJSON(rawToChar(raw_out),simplifyVector=FALSE),error=function(error)NULL)
  if(length(raw_err)||is.null(parsed)||!is.list(parsed)||is.null(names(parsed))) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  if(!is.null(status)&&as.integer(status)!=0L){if(identical(parsed$status,"blocked")) .data_statement_import_mapping_abort(parsed$code);.data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")}
  if(!identical(parsed$status,"complete")||!is.list(parsed$result)) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  parsed$result
}

validate_data_statement_exchange_preview_v1 <- function(value) {
  expected<-c("activation_authorized","activity_draft_write","adapter_id","canonical_write","cash_write","disposition_counts","mapping_rows","network_access","provider_access","rows","selected_period","silent_drop_count","source_fingerprint","source_row_count","statement_exchange_reward_adapter_version","status","tax_write")
  # Mehrere Dateien als ein Lauf (rc.343) tragen zusaetzlich Dateizahl und die Zeilen, die schon in einer anderen Datei standen.
  multi<-c("cross_file_duplicate_count","source_file_count")
  if(is.list(value)&&!is.null(names(value))&&all(multi%in%names(value))){
    files<-suppressWarnings(as.integer(value$source_file_count));dropped<-suppressWarnings(as.integer(value$cross_file_duplicate_count))
    if(length(files)!=1L||is.na(files)||files<2L||length(dropped)!=1L||is.na(dropped)||dropped<0L) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
    expected<-c(expected,multi)
  }
  if(!is.list(value)||is.null(names(value))||!identical(sort(names(value)),sort(expected))||!identical(value$status,"exchange_reward_adapter_projected_disabled")||as.integer(value$statement_exchange_reward_adapter_version)!=1L||as.integer(value$silent_drop_count)!=0L||length(value$rows)!=as.integer(value$source_row_count)) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  if(any(vapply(c("activation_authorized","activity_draft_write","canonical_write","cash_write","network_access","provider_access","tax_write"),function(field)!identical(value[[field]],FALSE),logical(1L)))) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  period<-value$selected_period
  if(!is.list(period)||!identical(sort(names(period)),c("end_date","start_date"))||any(is.na(as.Date(c(period$start_date,period$end_date))))||as.Date(period$start_date)>as.Date(period$end_date)) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  allowed<-c("reward_candidate_disabled","deferred","diagnostic","duplicate_deferred")
  dispositions<-vapply(value$rows,`[[`,character(1L),"disposition")
  if(any(!dispositions%in%allowed)||sum(unlist(value$disposition_counts,use.names=FALSE))!=as.integer(value$source_row_count)||length(value$mapping_rows)!=as.integer(value$disposition_counts$reward_candidate_disabled)) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  value
}

validate_data_statement_import_mapping_v1 <- function(value) {
  expected<-c("activity_draft_write","canonical_write","cash_write","disposition_counts","duplicate_source_row_count","network_access","provider_access","row_count","rows","silent_drop_count","statement_import_mapping_version","status","tax_write","tuple_count","tuple_inventory")
  if(!is.list(value)||is.null(names(value))||!identical(sort(names(value)),sort(expected))||!identical(value$status,"mapping_projected_no_write")||as.integer(value$statement_import_mapping_version)!=1L||as.integer(value$silent_drop_count)!=0L) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  negative<-c("activity_draft_write","canonical_write","cash_write","network_access","provider_access","tax_write")
  if(any(vapply(negative,function(field)!identical(value[[field]],FALSE),logical(1L)))||length(value$rows)!=as.integer(value$row_count)) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  dispositions<-vapply(value$rows,`[[`,character(1L),"disposition")
  if(any(!dispositions%in%c("draft_ready","draft_needs_valuation","mapping_required","deferred","duplicate_deferred"))||sum(unlist(value$disposition_counts,use.names=FALSE))!=as.integer(value$row_count)||length(value$tuple_inventory)!=as.integer(value$tuple_count)||as.integer(value$duplicate_source_row_count)!=as.integer(value$disposition_counts$duplicate_deferred)) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  value
}

.data_statement_import_mapping_profile_context <- function(context) {
  if(!exists("runtime_context_valid",mode="function")||!runtime_context_valid(context)) .data_statement_import_mapping_abort("statement_mapping_profile_context_invalid")
  list(data_space=runtime_data_space_path(context),context=list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id))
}

new_data_statement_import_mapping_v1 <- function(project_root,runner=NULL) {
  root<-normalizePath(project_root,winslash="/",mustWork=TRUE);execute<-if(is.null(runner))function(payload).data_statement_import_mapping_run(root,payload)else runner
  if(!is.function(execute)) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
  list(
    exchange_preview=function(source_path,adapter_id,confirmed_timezone,period_start_date=as.Date("1900-01-01"),period_end_date=Sys.Date()){
      dates<-as.Date(c(period_start_date,period_end_date))
      if(length(dates)!=2L||any(is.na(dates))||dates[[1L]]>dates[[2L]]) .data_statement_import_mapping_abort("statement_exchange_adapter_period_invalid")
      if(!.data_statement_import_mapping_path(source_path)||!file.exists(source_path)||dir.exists(source_path)||nzchar(Sys.readlink(source_path))) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
      size<-file.info(source_path)$size
      if(length(size)!=1L||is.na(size)||size<1||size>32000000) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
      con<-file(source_path,open="rb");on.exit(close(con),add=TRUE);raw<-readBin(con,"raw",n=as.integer(size)+1L)
      if(length(raw)!=as.integer(size)) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
      validate_data_statement_exchange_preview_v1(execute(list(operation="exchange_preview",source_base64=jsonlite::base64_enc(raw),adapter_id=adapter_id,confirmed_timezone=confirmed_timezone,period_start_date=format(dates[[1L]],"%Y-%m-%d"),period_end_date=format(dates[[2L]],"%Y-%m-%d"))))
    },
    # Alle Exporte einer Boerse als ein Lauf (rc.343); Ueberlappungen zaehlt der Leser einmal. Eine Datei verhaelt sich wie oben.
    exchange_preview_many=function(source_paths,adapter_id,confirmed_timezone,period_start_date=as.Date("1900-01-01"),period_end_date=Sys.Date()){
      dates<-as.Date(c(period_start_date,period_end_date))
      if(length(dates)!=2L||any(is.na(dates))||dates[[1L]]>dates[[2L]]) .data_statement_import_mapping_abort("statement_exchange_adapter_period_invalid")
      if(!is.character(source_paths)||!length(source_paths)||length(source_paths)>64L||anyNA(source_paths)) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
      encoded<-lapply(source_paths,function(source_path){
        if(!.data_statement_import_mapping_path(source_path)||!file.exists(source_path)||dir.exists(source_path)||nzchar(Sys.readlink(source_path))) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
        size<-file.info(source_path)$size
        if(length(size)!=1L||is.na(size)||size<1||size>32000000) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
        con<-file(source_path,open="rb");on.exit(close(con),add=TRUE);raw<-readBin(con,"raw",n=as.integer(size)+1L)
        if(length(raw)!=as.integer(size)) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
        jsonlite::base64_enc(raw)
      })
      validate_data_statement_exchange_preview_v1(execute(list(operation="exchange_preview_many",sources_base64=encoded,adapter_id=adapter_id,confirmed_timezone=confirmed_timezone,period_start_date=format(dates[[1L]],"%Y-%m-%d"),period_end_date=format(dates[[2L]],"%Y-%m-%d"))))
    },
    project=function(rows,mappings,adapter_id,adapter_version,base_currency,confirmed_timezone)validate_data_statement_import_mapping_v1(execute(list(operation="project",rows=rows,mappings=mappings,adapter_id=adapter_id,adapter_version=adapter_version,base_currency=base_currency,confirmed_timezone=confirmed_timezone))),
    profile_save=function(context,adapter_id,adapter_version,profile_label,mapping_rows,created_at_utc,profile_ref=NULL,expected_revision=NULL){binding<-.data_statement_import_mapping_profile_context(context);execute(c(list(operation="profile_save",adapter_id=adapter_id,adapter_version=adapter_version,profile_label=profile_label,mapping_rows=mapping_rows,created_at_utc=created_at_utc,profile_ref=profile_ref,expected_revision=expected_revision),binding))},
    profile_list=function(context,adapter_id,adapter_version){binding<-.data_statement_import_mapping_profile_context(context);execute(c(list(operation="profile_list",adapter_id=adapter_id,adapter_version=adapter_version),binding))},
    profile_read=function(context,profile_ref){binding<-.data_statement_import_mapping_profile_context(context);execute(c(list(operation="profile_read",profile_ref=profile_ref),binding))},
    profile_preview=function(profile,current_rows,asset_ids,account_ids)execute(list(operation="profile_preview",profile=profile,current_rows=current_rows,asset_ids=unname(as.list(asset_ids)),account_ids=unname(as.list(account_ids)))),
    derive_reward_manual_valuation=function(gross_quantity_decimal,asset_fee_quantity_decimal,mode,value_decimal,price_currency,expected_currency){
      result<-execute(list(operation="derive_reward_manual_valuation",gross_quantity_decimal=gross_quantity_decimal,asset_fee_quantity_decimal=asset_fee_quantity_decimal,mode=mode,value_decimal=value_decimal,price_currency=price_currency,expected_currency=expected_currency))
      required<-c("canonical_write","event_patch","mode","network_access","price_currency","provider_access","status","tax_write")
      if(!is.list(result)||!identical(sort(names(result)),sort(required))||!identical(result$status,"owner_manual_valuation_exact")||any(vapply(c("canonical_write","network_access","provider_access","tax_write"),function(field)!identical(result[[field]],FALSE),logical(1L)))) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
      result
    }
  )
}

data_statement_import_mapping_synthetic_v1 <- function(center,scenario="source_missing") {
  if(!scenario%in%c("source_missing","source_unit_price","source_fiat_total","foreign_currency")) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
  valuation<-switch(scenario,
    source_missing=list(source_value_mode="none",price_currency="EUR",source_unit_price_decimal=NULL,source_fiat_total_decimal=NULL),
    source_unit_price=list(source_value_mode="unit_price",price_currency="EUR",source_unit_price_decimal="12.3400",source_fiat_total_decimal=NULL),
    source_fiat_total=list(source_value_mode="fiat_total",price_currency="EUR",source_unit_price_decimal=NULL,source_fiat_total_decimal="10"),
    foreign_currency=list(source_value_mode="unit_price",price_currency="USD",source_unit_price_decimal="12.34",source_fiat_total_decimal=NULL)
  )
  event<-list(event_time_evidence="exact",local_date="2026-04-01",local_time="12:00:00",time_zone="Europe/Berlin",effective_at_utc="2026-04-01T10:00:00Z",original_acquired_time_evidence="not_applicable",original_acquired_local_date=NULL,original_acquired_local_time=NULL,original_acquired_time_zone=NULL,original_acquired_at_utc=NULL,quantity_decimal="1.1",eligible_quantity_decimal=NULL,gross_amount_decimal=NULL,monetary_fee_decimal=NULL,asset_fee_quantity_decimal="0.1",movement_context_code="not_applicable")
  rows<-list(
    list(source_row_ordinal=1L,source_row_key="invented_row_001",source_asset_key="INVENTED_ASSET_A",source_account_key="INVENTED_REWARD_ACCOUNT",event_type="reward",event_fields=event,valuation=valuation),
    list(source_row_ordinal=2L,source_row_key="invented_row_002",source_asset_key="INVENTED_ASSET_B",source_account_key="INVENTED_REWARD_ACCOUNT",event_type="reward",event_fields=event,valuation=valuation)
  )
  mappings<-list(
    list(source_asset_key="INVENTED_ASSET_A",source_account_key="INVENTED_REWARD_ACCOUNT",event_type="reward",disposition="map",target_asset_option_key="invented_asset_option",target_account_option_key="invented_account_option"),
    list(source_asset_key="INVENTED_ASSET_B",source_account_key="INVENTED_REWARD_ACCOUNT",event_type="reward",disposition="defer",target_asset_option_key=NULL,target_account_option_key=NULL)
  )
  center$project(rows,mappings,"invented_reward_statement_v1","1.0.0","EUR","Europe/Berlin")
}

data_statement_import_mapping_handoff_v1 <- function(value,draft_center,context,target_registry,portfolio_id=NULL,source_fingerprint,now_utc,progress_callback=NULL,booked_row_keys=character()) {
  value<-validate_data_statement_import_mapping_v1(value)
  portfolio_valid<-is.null(portfolio_id)||(is.character(portfolio_id)&&length(portfolio_id)==1L&&!is.na(portfolio_id)&&grepl("^ptf_[a-f0-9]{16,64}$",portfolio_id))
  draft_center_valid<-(inherits(draft_center,"spot_data_activity_draft_center_v1")&&is.environment(draft_center)&&is.function(draft_center$adapter$create_or_reuse))||(is.list(draft_center)&&is.function(draft_center$adapter$create_or_reuse))
  if(!draft_center_valid||!is.list(target_registry)||!is.list(target_registry$assets)||!is.list(target_registry$accounts)||!portfolio_valid||!is.character(source_fingerprint)||length(source_fingerprint)!=1L||is.na(source_fingerprint)||!grepl("^[a-f0-9]{64}$",source_fingerprint)||(!is.null(progress_callback)&&!is.function(progress_callback))) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
  resolve<-function(entries,key,pattern){
    entry<-entries[[key]]
    if(is.null(entry)||!is.list(entry)||!is.character(entry$target_id)||length(entry$target_id)!=1L||is.na(entry$target_id)||!grepl(pattern,entry$target_id)) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
    entry
  }
  written<-list();seen<-character();booked<-0L
  for(row in value$rows){
    if(!row$disposition%in%c("draft_ready","draft_needs_valuation"))next
    if(row$source_row_key%in%booked_row_keys){booked<-booked+1L;next}
    handoff<-row$draft_handoff;asset_entry<-resolve(target_registry$assets,handoff$target_asset_option_key,"^ast_[a-f0-9]{16,64}$");account_entry<-resolve(target_registry$accounts,handoff$target_account_option_key,"^acc_[a-f0-9]{16,64}$");asset_id<-asset_entry$target_id;account_id<-account_entry$target_id
    row_portfolio_id<-if(is.null(portfolio_id))account_entry$portfolio_id else portfolio_id
    if(!is.character(row_portfolio_id)||length(row_portfolio_id)!=1L||is.na(row_portfolio_id)||!grepl("^ptf_[a-f0-9]{16,64}$",row_portfolio_id)) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
    if(row$source_row_key%in%seen) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
    seen<-c(seen,row$source_row_key);event<-handoff$event_fields;event$asset_ref<-asset_id;event$account_ref<-account_id;event$related_account_ref<-NULL;event$source_asset_ref<-NULL
    source_binding<-list(source_fingerprint=source_fingerprint,source_row_ordinal=as.integer(row$source_row_ordinal),source_row_key=row$source_row_key)
    created<-if(inherits(draft_center,"spot_data_activity_draft_center_v1"))data_activity_draft_create_or_reuse_tolerant_csv_v1(draft_center,context,row_portfolio_id,event,source_binding,handoff$source_auxiliary,now_utc)else draft_center$adapter$create_or_reuse(context,row_portfolio_id,event,source_binding,handoff$source_auxiliary,now_utc)
    public_created<-if(is.list(created$public_draft))created$public_draft else created
    if(!is.list(created)||!is.character(public_created$status)||length(public_created$status)!=1L) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
    written[[length(written)+1L]]<-list(source_row_ordinal=as.integer(row$source_row_ordinal),draft_status=public_created$status,valuation_status=handoff$valuation_status,created_new=isTRUE(created$created_new),reused_existing=isTRUE(created$reused_existing))
    if(!is.null(progress_callback))progress_callback(length(written),sum(vapply(value$rows,function(item)item$disposition%in%c("draft_ready","draft_needs_valuation")&&!item$source_row_key%in%booked_row_keys,logical(1L))))
  }
  list(status="statement_mapping_activity_drafts_prepared",prepared_draft_count=as.integer(length(written)),already_booked_count=booked,valuation_pending_count=as.integer(sum(vapply(written,function(row)identical(row$valuation_status,"valuation_pending"),logical(1L)))),rows=written,duplicate_source_row_count=as.integer(value$duplicate_source_row_count),silent_drop_count=0L,canonical_write=FALSE,cash_write=FALSE,provider_access=FALSE,network_access=FALSE,tax_write=FALSE)
}

data_statement_import_mapping_rows_v1 <- function(value,booked_row_keys=character()) {
  value<-validate_data_statement_import_mapping_v1(value)
  is_booked<-function(row)row$source_row_key%in%booked_row_keys
  disposition_label<-c(draft_ready="Bereit",draft_needs_valuation="Bewertung später ergänzen",mapping_required="Zuordnung offen",deferred="Zurückgestellt",duplicate_deferred="Duplikat zurückgestellt")
  reason_label<-c(source_fiat_total_exactly_projected="Vollständig · Wert aus dem Auszug (Gesamtbetrag)",source_unit_price_exact="Vollständig · Wert aus dem Auszug (Stückpreis)",source_valuation_missing="Kein Wert im Auszug · Kurs später ergänzen",mapped_source_value="Zuordnung und Bewertung vollständig",mapped_valuation_pending="Zuordnung vollständig; Bewertung offen",source_currency_conversion_required="Wert aus dem Auszug in Fremdwährung · Umrechnung mit gespeichertem Devisenkurs",mapping_required="Asset oder Konto noch auswählen",owner_deferred="Bewusst zurückgestellt",duplicate_source_row_key="Bereits enthalten")
  data.frame(
    Zeile=vapply(value$rows,function(row)as.integer(row$source_row_ordinal),integer(1L)),
    Status=vapply(value$rows,function(row)if(is_booked(row))"Bereits gebucht"else if(row$disposition%in%names(disposition_label))unname(disposition_label[[row$disposition]])else"Zu prüfen",character(1L)),
    Bewertung=vapply(value$rows,function(row)if(is.null(row$draft_handoff))"—"else if(identical(row$draft_handoff$valuation_status,"valuation_pending"))"Offen"else"Aus Quelle vorhanden",character(1L)),
    Hinweis=vapply(value$rows,function(row)if(is_booked(row))"Gleiche Buchung vorhanden (Asset, Konto, Zeitpunkt, Menge) – wird nicht erneut übernommen"else if(row$reason_code%in%names(reason_label))unname(reason_label[[row$reason_code]])else"Bitte prüfen",character(1L)),
    stringsAsFactors=FALSE,check.names=FALSE
  )
}

data_statement_import_mapping_tuples_v1 <- function(value) {
  value<-validate_data_statement_import_mapping_v1(value)
  if(!length(value$tuple_inventory))return(data.frame())
  data.frame(
    `Quell-Asset`=vapply(value$tuple_inventory,`[[`,character(1L),"source_asset_key"),
    `Quellkonto`=vapply(value$tuple_inventory,`[[`,character(1L),"source_account_key"),
    Ereignis=vapply(value$tuple_inventory,`[[`,character(1L),"event_type"),
    Zeilen=vapply(value$tuple_inventory,function(row)as.integer(row$source_row_count),integer(1L)),
    Zuordnung=vapply(value$tuple_inventory,`[[`,character(1L),"mapping_status"),
    stringsAsFactors=FALSE,check.names=FALSE
  )
}

data_statement_exchange_preview_tuples_v1 <- function(value,base_currency="EUR") {
  value<-validate_data_statement_exchange_preview_v1(value)
  if(!length(value$mapping_rows))return(data.frame())
  keys<-vapply(value$mapping_rows,function(row)paste(row$source_asset_key,row$source_account_key,row$event_type,sep="\r"),character(1L))
  unique_keys<-unique(keys)
  data.frame(
    `Quell-Asset`=vapply(unique_keys,function(key)strsplit(key,"\r",fixed=TRUE)[[1L]][[1L]],character(1L)),
    `Quellkonto`=vapply(unique_keys,function(key)strsplit(key,"\r",fixed=TRUE)[[1L]][[2L]],character(1L)),
    Vorgang=vapply(unique_keys,function(key)strsplit(key,"\r",fixed=TRUE)[[1L]][[3L]],character(1L)),
    Zeilen=vapply(unique_keys,function(key)sum(keys==key),integer(1L)),
    Bewertung=vapply(unique_keys,function(key){rows<-value$mapping_rows[keys==key]
      has<-vapply(rows,function(row)!identical(row$valuation$source_value_mode,"none"),logical(1L))
      foreign<-unique(unlist(lapply(rows[has],function(row){currency<-row$valuation$price_currency;if(is.character(currency)&&length(currency)==1L&&!identical(currency,base_currency))currency else NULL})))
      label<-if(all(has))"Aus dem Auszug"else if(!any(has))"Kein Wert im Auszug · Kurs ergänzen"else sprintf("%d aus dem Auszug · %d ohne Wert",sum(has),sum(!has))
      if(length(foreign))paste0(label," (",paste(foreign,collapse=", "),") · Umrechnung in ",base_currency," nötig")else label},character(1L)),
    stringsAsFactors=FALSE,check.names=FALSE
  )
}

data_statement_import_mapping_profile_rows_v1 <- function(tuples,asset_refs,account_refs,target_asset_id,target_account_id) {
  if(!is.data.frame(tuples)||!all(c("Quell-Asset","Quellkonto","Vorgang")%in%names(tuples))||!is.character(asset_refs)||!is.character(account_refs)||length(asset_refs)!=nrow(tuples)||length(account_refs)!=nrow(tuples)||!is.function(target_asset_id)||!is.function(target_account_id)) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
  lapply(seq_len(nrow(tuples)),function(index){
    asset_ref<-asset_refs[[index]];account_ref<-account_refs[[index]];mapped<-nzchar(asset_ref)&&nzchar(account_ref)
    list(source_asset_key=tuples$`Quell-Asset`[[index]],source_account_key=tuples$`Quellkonto`[[index]],event_type=tuples$Vorgang[[index]],disposition=if(mapped)"map"else"defer",target_asset_id=if(mapped)target_asset_id(asset_ref)else NULL,target_account_id=if(mapped)target_account_id(account_ref)else NULL)
  })
}

data_statement_import_mapping_profile_defaults_v1 <- function(tuples,profile,asset_ref_for_id,account_ref_for_id) {
  if(!is.data.frame(tuples)||!all(c("Quell-Asset","Quellkonto","Vorgang")%in%names(tuples))||!is.list(profile)||!is.list(profile$mapping_rows)||!is.function(asset_ref_for_id)||!is.function(account_ref_for_id)) .data_statement_import_mapping_abort("data_statement_import_mapping_input_invalid")
  stored<-setNames(profile$mapping_rows,vapply(profile$mapping_rows,function(row)paste(row$source_asset_key,row$source_account_key,row$event_type,sep="\r"),character(1L)))
  assets<-accounts<-rep("",nrow(tuples));stale<-0L
  for(index in seq_len(nrow(tuples))){
    key<-paste(tuples$`Quell-Asset`[[index]],tuples$`Quellkonto`[[index]],tuples$Vorgang[[index]],sep="\r");row<-stored[[key]]
    if(is.null(row)||!identical(row$disposition,"map"))next
    asset<-tryCatch(asset_ref_for_id(row$target_asset_id),error=function(error)"");account<-tryCatch(account_ref_for_id(row$target_account_id),error=function(error)"")
    if(!nzchar(asset)||!nzchar(account)){stale<-stale+1L;next}
    assets[[index]]<-asset;accounts[[index]]<-account
  }
  list(asset_refs=assets,account_refs=accounts,stale_target_count=as.integer(stale))
}

data_statement_import_mapping_user_message_v1 <- function(error_code) {
  # Codes des Leser-Plugins der Boerse (rc.377): je Grund ein eigener Satz.
  reader<-if(exists("data_statement_reader_message_v1",mode="function"))data_statement_reader_message_v1(if(is.character(error_code))error_code else "","Reward-Leser der gewählten Börse","Es wurden keine Daten geschrieben.") else NULL
  if(!is.null(reader))return(paste0(reader$title,": ",reader$copy))
  messages<-c(
    statement_exchange_adapter_header_invalid="Das Dateiformat wurde nicht eindeutig erkannt. Bitte die gewählte Börse prüfen; die Datei wurde nicht verändert.",
    statement_exchange_adapter_source_invalid="Die Datei konnte nicht vollständig gelesen werden. Gültige Zeilen bleiben unverändert; bitte Datei und Zeichensatz prüfen.",
    statement_exchange_adapter_timezone_invalid="Für die Zeitangaben wird noch eine Zeitzone benötigt.",
    statement_exchange_adapter_profile_invalid="Das gewählte Börsenformat passt nicht zur Datei. Bitte eine andere Börse auswählen.",
    statement_exchange_adapter_overlay_invalid="Eigene Formatbeschreibungen gibt es nicht mehr; ein eigenes Format braucht ein Leser-Plugin.",
    statement_exchange_adapter_period_invalid="Bitte einen vollständigen Reward-Zeitraum mit Von-Datum bis Bis-Datum auswählen."
  )
  if(is.character(error_code)&&length(error_code)==1L&&!is.na(error_code)&&error_code%in%names(messages))unname(messages[[error_code]]) else "Die Vorschau konnte nicht erstellt werden. Es wurden keine Daten geschrieben."
}

# Gruende in Saetzen (#520, Festlegung 28.10.2026): Bricht im Reward-Import die Pruefung oder das Buchen ab, nennt die Karte einen
# Satz und die Abhilfe. Der Code steht nur aufklappbar darunter (`code`), statt eines rohen Codes im Text.
data_statement_reward_error_v1 <- function(step,error=NULL) {
  code<-if(is.list(error)&&is.character(error$code)&&length(error$code)==1L&&!is.na(error$code)&&nzchar(error$code))error$code else "data_activity_draft_adapter_failed"
  base<-switch(step,
    validate="Die Prüfung ist abgebrochen; gebucht wurde nichts.",
    resume="Der Lauf ließ sich nicht laden; geändert wurde nichts.",
    book="Die Buchung ist abgebrochen. Was bis dahin gebucht wurde, bleibt gebucht und zählt beim nächsten Versuch als vorhanden.",
    stop("data_statement_reward_error_step_invalid",call.=FALSE))
  remedy<-if(grepl("lock_unavailable",code,fixed=TRUE))"Gerade schreibt ein anderer Vorgang, etwa „Alles aktualisieren“. Kurz warten und erneut versuchen."
    else if(grepl("generation_conflict|plan_stale|canonical_changed|preview_stale|confirmation_expired|state_conflict",code))"Der Bestand hat sich seit der Prüfung geändert. Erneut prüfen, danach lässt sich buchen."
    else if(grepl("fifo_invalid|inventory_insufficient",code))"Der Kern hat abgelehnt, weil ein Bestand danach nicht aufginge. „Gründe anzeigen“ unter „Blockierte Rewards“ nennt den Reward."
    else if(grepl("storage_invalid",code,fixed=TRUE))"Eine Datei im Datenraum ist nicht lesbar. Bitte nicht wiederholt versuchen; die Diagnose unten nennt den Schritt."
    else "Erneut versuchen. Bleibt es dabei, nennt die Diagnose unten den Schritt."
  list(tone="error",title=switch(step,validate="Prüfung nicht möglich",resume="Fortsetzen nicht möglich",book="Buchung nicht möglich"),copy=paste(base,remedy),code=code)
}

# Der Code zur Meldung, zugeklappt.
data_statement_reward_error_code_ui_v1 <- function(result) {
  if(!is.list(result)||!is.character(result$code)||length(result$code)!=1L||!nzchar(result$code))return(NULL)
  shiny::tags$details(class="pl-disclosure",shiny::tags$summary("Technischer Code"),shiny::tags$code(result$code))
}

data_statement_exchange_preview_status_v1 <- function(value=NULL,error_code=NULL) {
  if(!is.null(error_code))return(list(tone="warning",title="Datei benötigt eine kurze Prüfung",copy=data_statement_import_mapping_user_message_v1(error_code)))
  if(is.null(value))return(list(tone="neutral",title="Vorschau des Auszugs bereit",copy="Datei und Börse auswählen. Technische Identitätsprüfungen laufen unsichtbar im Hintergrund."))
  counts<-value$disposition_counts
  outside<-sum(vapply(value$rows,function(row)identical(row$reason_code,"outside_selected_period"),logical(1L)))
  other_deferred<-as.integer(counts$deferred)-outside
  period<-value$selected_period
  list(tone=if(as.integer(counts$diagnostic)>0L)"warning"else"success",title="Auszug erkannt",copy=sprintf("Zeitraum %s bis %s · %d Zeilen · %d Rewards im Zeitraum · %d außerhalb · %d andere Vorgänge zurückgestellt · %d Zeilen zu prüfen · %d Duplikate · nichts still verworfen",period$start_date,period$end_date,value$source_row_count,counts$reward_candidate_disabled,outside,other_deferred,counts$diagnostic,counts$duplicate_deferred))
}

data_statement_import_mapping_status_v1 <- function(value=NULL,error_code=NULL) {
  if(!is.null(error_code))return(list(tone="blocked",title="Zuordnung des Auszugs blockiert",copy=data_statement_import_mapping_user_message_v1(error_code)))
  if(is.null(value))return(list(tone="neutral",title="Allgemeine Zuordnung des Auszugs bereit",copy="Noch keine erfundene Projektion ausgeführt; normale Adapter bleiben deaktiviert."))
  counts<-value$disposition_counts
  list(tone=if(as.integer(counts$mapping_required)>0L)"warning"else"success",title="Vollständige Projektion von Zuordnung und Bewertung",copy=sprintf("%d Zeilen · %d Kombinationen · %d bereit für den Entwurf · %d Bewertung offen · %d zurückgestellt · %d Duplikate zurückgestellt · 0 still verworfen",value$row_count,value$tuple_count,counts$draft_ready,counts$draft_needs_valuation,counts$deferred,value$duplicate_source_row_count))
}

# Candidates for the cross-file "already booked" check. IDs stay server-side;
# the source row key identifies the candidate only within this preview.
data_statement_reward_booked_candidates_v1 <- function(value,target_registry) {
  value<-validate_data_statement_import_mapping_v1(value);candidates<-list()
  for(row in value$rows){
    if(!row$disposition%in%c("draft_ready","draft_needs_valuation"))next
    handoff<-row$draft_handoff;asset<-target_registry$assets[[handoff$target_asset_option_key]];account<-target_registry$accounts[[handoff$target_account_option_key]];fields<-handoff$event_fields
    if(is.null(asset)||is.null(account)||!identical(fields$event_type,"reward")||!identical(fields$event_time_evidence,"exact"))next
    candidates[[length(candidates)+1L]]<-list(candidate_key=row$source_row_key,asset_id=asset$target_id,account_id=account$target_id,local_date=fields$local_date,local_time=fields$local_time,time_zone=fields$time_zone,quantity_decimal=fields$quantity_decimal)
  }
  candidates
}

data_statement_reward_booked_match_v1 <- function(project_root,context,candidates) {
  if(!length(candidates))return(character())
  payload<-list(context=list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id,actor_id=context$actor_id,role="desktop_owner"),data_space_path=runtime_data_space_path(context),candidates=candidates)
  value<-.per_asset_review_adapter_run(project_root,"reward-booked-match",payload)
  keys<-value$match$matched_candidate_keys
  if(!is.list(keys)&&!is.character(keys)) .data_statement_import_mapping_abort("data_statement_import_mapping_boundary_failed")
  as.character(unlist(keys))
}

# Kennung der Boerse an gebuchten Rewards (rc.345): nach dem Buchen aus der gebuchten Datei und der Ablage in den Belegspeicher. Die
# Buchung steht dann schon; scheitert dieser Schritt, bleibt sie, und gemeldet wird nur, dass die Kennungen fehlen (NULL).
data_statement_reward_references_record_v1 <- function(project_root,context,adapter_id,source_paths=character(),now_utc) {
  if(!is.character(adapter_id)||length(adapter_id)!=1L||is.na(adapter_id)||!nzchar(adapter_id))return(NULL)
  paths<-as.character(source_paths[is.character(source_paths)&!is.na(source_paths)&nzchar(source_paths)])
  payload<-list(context=list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id,actor_id=context$actor_id,role="desktop_owner"),
    data_space_path=runtime_data_space_path(context),adapter_id=adapter_id,source_paths=I(paths),recorded_at_utc=now_utc)
  value<-tryCatch(.per_asset_review_adapter_run(project_root,"reward-references-record",payload),error=function(error)NULL)
  if(!is.list(value)||!is.list(value$references))return(NULL)
  value$references
}

# Der Satz dazu in der Meldung nach dem Buchen; nichts, wenn nichts geschrieben wurde.
data_statement_reward_references_note_v1 <- function(references) {
  written<-if(is.list(references)&&is.numeric(references$written_count))as.integer(references$written_count)else 0L
  if(written>0L)sprintf("%d Kennungen der Börse im Belegspeicher",written)else NULL
}

# Account default: a saved account for one tuple of the same source account
# applies to the other tuples of that source account. `skip`: source accounts that
# name only the exchange, not a sub-account - they neither give nor take.
data_statement_import_mapping_propagate_accounts_v1 <- function(tuples,account_refs,skip=character()) {
  for(index in seq_len(nrow(tuples))){
    if(nzchar(account_refs[[index]])||tuples$`Quellkonto`[[index]]%in%skip)next
    same<-which(tuples$`Quellkonto`==tuples$`Quellkonto`[[index]]&nzchar(account_refs))
    candidates<-unique(account_refs[same]);if(length(candidates)==1L)account_refs[[index]]<-candidates[[1L]]
  }
  account_refs
}

# Leser, deren Export ein Unterkonto nennt (Kraken: Spot, Earn), mit dem Namen, den der Leser ohne Angabe setzt. Nur dort heisst
# "gleiches Boersenkonto" auch "gleiches Wallet"; bei Coinbase, Bison und BSDEX steht ueberall nur der Boersenname, und ein neuer
# Coin erbte das Konto der anderen, etwa ein Staking-Konto. Seit rc.425 (#486)
# aus dem Manifest des Lesers (`subaccount_fallback`), ueber die Liste der angebotenen Leser; bis rc.424 eine feste Liste hier.
data_statement_named_subaccounts_v1 <- function(offered) {
  readers <- if (is.list(offered) && is.list(offered$readers)) offered$readers else list()
  named <- Filter(function(reader) identical(reader$domain, "reward") && is.character(reader$reader_id) && length(reader$reader_id) == 1L &&
    is.character(reader$subaccount_fallback) && length(reader$subaccount_fallback) == 1L && nzchar(reader$subaccount_fallback), readers)
  stats::setNames(vapply(named, function(reader) reader$subaccount_fallback, character(1L)), vapply(named, function(reader) reader$reader_id, character(1L)))
}

# Kontovorschlag (rc.343): fuellt nur leere Konten, deren Asset schon gewaehlt ist. `suggest` liefert asset_id -> account_id
# (das Konto der Boerse mit dem juengsten Reward dieses Coins usw.); `asset_id` und `account_ref` uebersetzen zwischen Auswahl und
# Kennung. Was sich nicht uebersetzen laesst oder fehlschlaegt, bleibt offen.
data_statement_import_mapping_suggest_accounts_v1 <- function(asset_refs,account_refs,suggest,asset_id,account_ref) {
  open<-which(!nzchar(account_refs)&nzchar(asset_refs));if(!length(open))return(account_refs)
  ids<-vapply(asset_refs[open],function(ref){id<-tryCatch(asset_id(ref),error=function(error)NULL);if(is.character(id)&&length(id)==1L&&nzchar(id))id else NA_character_},character(1L),USE.NAMES=FALSE)
  known<-unique(ids[!is.na(ids)]);if(!length(known))return(account_refs)
  suggested<-tryCatch(suggest(known),error=function(error)list())
  for(position in seq_along(open)){
    id<-ids[[position]];if(is.na(id))next
    account<-suggested[[id]];if(!is.character(account)||length(account)!=1L||!nzchar(account))next
    ref<-tryCatch(account_ref(account),error=function(error)NULL)
    if(is.character(ref)&&length(ref)==1L&&nzchar(ref))account_refs[[open[[position]]]]<-ref
  }
  account_refs
}

# Asset default: a unique catalog Asset named exactly like the source symbol or
# "SYMBOL (Name)". Ambiguous or missing names stay open for the owner.
data_statement_import_mapping_suggest_assets_v1 <- function(tuples,asset_refs,catalog_assets) {
  labels<-vapply(catalog_assets,function(row)as.character(row$label),character(1L));refs<-vapply(catalog_assets,function(row)as.character(row$ref),character(1L))
  for(index in seq_len(nrow(tuples))){
    if(nzchar(asset_refs[[index]]))next
    key<-toupper(tuples$`Quell-Asset`[[index]]);hits<-which(toupper(labels)==key|startsWith(toupper(labels),paste0(key," (")))
    if(length(hits)==1L)asset_refs[[index]]<-refs[[hits]]
  }
  asset_refs
}

# Owner-facing text for valuation blocks (no raw codes in the standard view).
data_statement_reward_valuation_message_v1 <- function(code) {
  switch(as.character(code),
    desktop_reward_daily_close_asset_history_missing="Für diesen Tag liegt noch kein Tageskurs des Assets vor. Marktdaten aktualisieren oder Wert manuell eintragen.",
    desktop_reward_daily_close_fx_history_missing=,fx_history_store_invalid="Für diesen Tag liegt noch kein Devisenkurs für die Umrechnung vor. FX-Daten aktualisieren oder Wert manuell eintragen.",
    desktop_reward_daily_close_ambiguous_listing="Für das Asset gibt es mehrere Kursquellen; bitte im Tab Marktdaten eine eindeutige Zuordnung festlegen oder Wert manuell eintragen.",
    "Die gespeicherten Kurse reichen für diese Bewertung nicht aus. Wert manuell eintragen oder Marktdaten prüfen.")
}

# Groups blocked valuations by asset and missing data: "ETH (Ethereum) · Tageskurs fehlt ab … · 2 Rewards".
data_statement_reward_missing_summary_v1 <- function(preview,batch,asset_label) {
  if(!is.list(preview)||!length(preview$dispositions)||!is.list(batch))return(character())
  blocked<-Filter(function(row)identical(row$disposition,"valuation_blocked"),preview$dispositions);if(!length(blocked))return(character())
  drafts<-batch$drafts;find<-function(ordinal){hits<-Filter(function(row)identical(as.integer(row$source_row_ordinal),as.integer(ordinal)),drafts);if(length(hits))hits[[1L]]else NULL}
  what<-c(desktop_reward_daily_close_asset_history_missing="Tageskurs fehlt",desktop_reward_daily_close_fx_history_missing="Devisenkurs fehlt",fx_history_store_invalid="Devisenkurs fehlt",desktop_reward_daily_close_ambiguous_listing="Kursquelle nicht eindeutig")
  rows<-lapply(blocked,function(item){draft<-find(item$source_row_ordinal);if(is.null(draft))return(NULL)
    reason<-if(!is.null(item$error_code)&&item$error_code%in%names(what))what[[item$error_code]]else"Kurs fehlt"
    currency<-draft$valuation_summary$price_currency;if(identical(unname(what[item$error_code]),"Devisenkurs fehlt")&&is.character(currency)&&nzchar(currency))reason<-paste0(reason," (",currency," → EUR)")
    list(asset=asset_label(draft$asset_ref),reason=reason,date=as.character(draft$event_summary$local_date))})
  rows<-Filter(Negate(is.null),rows);if(!length(rows))return(character())
  keys<-vapply(rows,function(row)paste(row$asset,row$reason,sep="\r"),character(1L))
  vapply(unique(keys),function(key){group<-rows[keys==key];first<-min(vapply(group,`[[`,character(1L),"date"))
    sprintf("%s · %s ab %s · %d Reward%s",group[[1L]]$asset,group[[1L]]$reason,format(as.Date(first),"%d.%m.%Y"),length(group),if(length(group)==1L)""else"s")},character(1L),USE.NAMES=FALSE)
}
