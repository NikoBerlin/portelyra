data_activity_quick_import_error_codes_v1 <- function() c(
  "data_activity_quick_import_state_invalid", "data_activity_quick_import_context_invalid",
  "data_activity_quick_import_source_required", "data_activity_quick_import_mapping_required",
  "data_activity_quick_import_prepare_required", "data_activity_quick_import_confirmation_required",
  "data_activity_quick_import_adapter_failed"
)

.data_activity_quick_abort <- function(code) {
  if(!is.character(code)||length(code)!=1L||is.na(code)||!code%in%data_activity_quick_import_error_codes_v1())stop("unregistered_data_activity_quick_import_error",call.=FALSE)
  stop(structure(list(message=code,call=NULL,code=code),class=c("spot_data_activity_quick_import_error","error","condition")))
}

.data_activity_quick_context <- function(context) {
  if(!isTRUE(tryCatch(runtime_context_valid(context),error=function(error)FALSE))||!identical(context$runtime_mode,"desktop_product")||!identical(context$role,"desktop_owner")) .data_activity_quick_abort("data_activity_quick_import_context_invalid")
  context
}

.data_activity_quick_call <- function(callback) tryCatch(
  callback(),
  spot_desktop_product_adapter_domain_error=function(error)stop(error),
  spot_data_activity_draft_error=function(error)stop(error),
  error=function(error).data_activity_quick_abort("data_activity_quick_import_adapter_failed")
)

.data_activity_quick_text <- function(value) {
  if(is.null(value)||!is.character(value)||length(value)!=1L||is.na(value))return("")
  value
}

.data_activity_quick_value <- function(value) {
  value<-.data_activity_quick_text(value)
  if(nzchar(value))value else NULL
}

.data_activity_quick_scalar_ref <- function(value,optional=FALSE) {
  if(optional&&(is.null(value)||identical(value,"")))return("")
  if(!is.character(value)||length(value)!=1L||is.na(value)||!nzchar(value)||value!=trimws(value)||nchar(value,type="bytes")>512L||grepl("[[:cntrl:]]",value)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  value
}

.data_activity_quick_mapping_entries <- function(entries) {
  if(is.null(entries))return(list())
  if(!is.list(entries)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  rows<-lapply(entries,function(entry){
    if(!is.list(entry)||!identical(names(entry),c("source_key","target_ref"))) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
    list(source_key=.data_activity_quick_scalar_ref(entry$source_key),target_ref=.data_activity_quick_scalar_ref(entry$target_ref))
  })
  keys<-vapply(rows,`[[`,character(1L),"source_key")
  if(anyDuplicated(keys)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  rows
}

.data_activity_quick_profile_new <- function(context,mapping_mode,default_portfolio_ref,default_account_ref,default_asset_ref,portfolio_mappings,account_mappings,asset_mappings) {
  .data_activity_quick_context(context)
  if(!mapping_mode%in%c("single_default","explicit_key_mapping")) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  structure(list(
    profile_version=1L,mapping_mode=mapping_mode,
    context_fingerprint=runtime_context_fingerprint(context),role="desktop_owner",
    default_portfolio_ref=.data_activity_quick_scalar_ref(default_portfolio_ref),
    default_account_ref=.data_activity_quick_scalar_ref(default_account_ref),
    default_asset_ref=.data_activity_quick_scalar_ref(default_asset_ref,optional=identical(mapping_mode,"explicit_key_mapping")),
    portfolio_mappings=.data_activity_quick_mapping_entries(portfolio_mappings),
    account_mappings=.data_activity_quick_mapping_entries(account_mappings),
    asset_mappings=.data_activity_quick_mapping_entries(asset_mappings)
  ),class="spot_data_activity_quick_profile_v1")
}

new_data_activity_quick_profile_v1 <- function(context,portfolio_ref,asset_ref,default_account_ref) {
  .data_activity_quick_profile_new(context,"single_default",portfolio_ref,default_account_ref,asset_ref,list(),list(),list())
}

new_data_activity_quick_mapping_profile_v1 <- function(
  context,default_portfolio_ref,default_account_ref,
  portfolio_mappings=list(),account_mappings=list(),asset_mappings=list()
) {
  .data_activity_quick_profile_new(
    context,"explicit_key_mapping",default_portfolio_ref,default_account_ref,
    "",portfolio_mappings,account_mappings,asset_mappings
  )
}

new_data_activity_quick_import_v1 <- function(adapter,draft_center,activity_editor) {
  required<-c("resolve_time","inspect_redundant","create","create_or_reuse","update","resolve_fee","bind_fifo_order","read","validate","confirmation","apply","resume","list","profile_save","profile_list","profile_read")
  if(!is.list(adapter)||!all(required%in%names(adapter))||anyDuplicated(names(adapter))||!all(vapply(adapter,is.function,logical(1L)))||!inherits(draft_center,"spot_data_activity_draft_center_v1")||!inherits(activity_editor,"spot_data_asset_activity_editor_v1")) .data_activity_quick_abort("data_activity_quick_import_state_invalid")
  center<-new.env(hash=FALSE,parent=emptyenv())
  center$adapter<-adapter;center$draft_center<-draft_center;center$activity_editor<-activity_editor
  center$inspection<-NULL;center$requirements<-NULL;center$prepared<-NULL
  center$profile_entries<-new.env(hash=TRUE,parent=emptyenv());center$profile_sequence<-0L
  class(center)<-"spot_data_activity_quick_import_v1";center
}

.data_activity_quick_check <- function(center) {
  if(!inherits(center,"spot_data_activity_quick_import_v1")||!is.environment(center)) .data_activity_quick_abort("data_activity_quick_import_state_invalid")
}

.data_activity_quick_requirement_rows <- function(rows,key_fields,name_fields) {
  references<-list();index<-0L
  for(row in rows)for(position in seq_along(key_fields)){
    key<-.data_activity_quick_text(row[[key_fields[[position]]]])
    if(!nzchar(key))next
    index<-index+1L
    references[[index]]<-list(source_key=key,source_name=.data_activity_quick_text(row[[name_fields[[position]]]]))
  }
  if(!length(references))return(list())
  keys<-sort(unique(vapply(references,`[[`,character(1L),"source_key")))
  lapply(keys,function(key){
    selected<-Filter(function(value)identical(value$source_key,key),references)
    names_seen<-sort(unique(Filter(nzchar,vapply(selected,`[[`,character(1L),"source_name"))))
    label<-if(length(names_seen)==1L)paste(key,"·",names_seen[[1L]])else key
    list(source_key=key,source_label=label,row_count=as.integer(length(selected)))
  })
}

.data_activity_quick_requirements <- function(rows) list(
  portfolios=.data_activity_quick_requirement_rows(rows,c("portfolio_key"),c("portfolio_name")),
  accounts=.data_activity_quick_requirement_rows(rows,c("account_key","related_account_key"),c("account_name","related_account_name")),
  assets=.data_activity_quick_requirement_rows(rows,c("asset_key","source_asset_key"),c("asset_name","source_asset_name"))
)

data_activity_quick_inspect_v1 <- function(center,context,source_path) {
  .data_activity_quick_check(center);.data_activity_quick_context(context)
  if(!is.character(source_path)||length(source_path)!=1L||is.na(source_path)||!file.exists(source_path)||dir.exists(source_path)) .data_activity_quick_abort("data_activity_quick_import_source_required")
  value<-.data_activity_quick_call(function()center$adapter$inspect_redundant(context,source_path))
  if(!is.list(value)||!is.list(value$public_inspection)||!is.list(value$trusted_rows)||length(value$trusted_rows)!=value$public_inspection$row_count||!is.character(value$source_fingerprint)||length(value$source_fingerprint)!=1L||is.na(value$source_fingerprint)||!grepl("^[a-f0-9]{64}$",value$source_fingerprint)) .data_activity_quick_abort("data_activity_quick_import_adapter_failed")
  rows<-Filter(function(row)identical(row$row_kind,"activity"),value$trusted_rows)
  requirements<-.data_activity_quick_requirements(rows)
  center$inspection<-value;center$requirements<-requirements;center$prepared<-NULL
  list(
    status=value$public_inspection$status,row_count=as.integer(value$public_inspection$row_count),
    activity_row_count=as.integer(length(rows)),
    asset_only_row_count=as.integer(sum(vapply(value$trusted_rows,function(row)identical(row$row_kind,"asset"),logical(1L)))),
    ready_row_count=as.integer(value$public_inspection$ready_row_count),
    needs_input_row_count=as.integer(value$public_inspection$needs_input_row_count),
    blocked_row_count=as.integer(value$public_inspection$blocked_row_count),
    single_asset_key=length(requirements$assets)<=1L,
    mapping_requirements=requirements,
    portfolio_mapping_key_count=as.integer(length(requirements$portfolios)),
    account_mapping_key_count=as.integer(length(requirements$accounts)),
    asset_mapping_key_count=as.integer(length(requirements$assets)),
    canonical_write=FALSE,path_exposed=FALSE,browser_internal_id_exposed=FALSE,fingerprint_exposed=FALSE
  )
}

.data_activity_quick_resolve_entries <- function(selection,entries,area) lapply(entries,function(entry)list(
  source_key=entry$source_key,target=.data_asset_activity_resolve(selection,area,entry$target_ref)
))

.data_activity_quick_profile <- function(center,context,profile) {
  if(!inherits(profile,"spot_data_activity_quick_profile_v1")||!identical(profile$context_fingerprint,runtime_context_fingerprint(context))||!identical(profile$role,"desktop_owner")||!profile$mapping_mode%in%c("single_default","explicit_key_mapping")) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  selection<-.data_asset_activity_selection(center$activity_editor,context)
  list(
    mapping_mode=profile$mapping_mode,
    default_portfolio=.data_asset_activity_resolve(selection,"portfolios",profile$default_portfolio_ref),
    default_account=.data_asset_activity_resolve(selection,"accounts",profile$default_account_ref),
    default_asset=.data_asset_activity_resolve(selection,"assets",profile$default_asset_ref,optional=TRUE),
    portfolio_mappings=.data_activity_quick_resolve_entries(selection,profile$portfolio_mappings,"portfolios"),
    account_mappings=.data_activity_quick_resolve_entries(selection,profile$account_mappings,"accounts"),
    asset_mappings=.data_activity_quick_resolve_entries(selection,profile$asset_mappings,"assets")
  )
}

.data_activity_quick_profile_target_rows <- function(entries,id_field) lapply(entries,function(entry)list(
  source_key=entry$source_key,target_id=entry$target[[id_field]]
))

data_activity_quick_mapping_profile_save_v1 <- function(center,context,profile,profile_label,is_standard,now_utc) {
  .data_activity_quick_check(center);.data_activity_quick_context(context)
  if(!inherits(profile,"spot_data_activity_quick_profile_v1")||!identical(profile$mapping_mode,"explicit_key_mapping")||!is.character(profile_label)||length(profile_label)!=1L||is.na(profile_label)||!nzchar(profile_label)||!is.logical(is_standard)||length(is_standard)!=1L||is.na(is_standard)||is.na(as.POSIXct(now_utc,format="%Y-%m-%dT%H:%M:%SZ",tz="UTC"))) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  resolved<-.data_activity_quick_profile(center,context,profile)
  value<-.data_activity_quick_call(function()center$adapter$profile_save(
    context,profile_label,isTRUE(is_standard),resolved$default_portfolio$portfolio_id,
    resolved$default_account$account_id,
    .data_activity_quick_profile_target_rows(resolved$portfolio_mappings,"portfolio_id"),
    .data_activity_quick_profile_target_rows(resolved$account_mappings,"account_id"),
    .data_activity_quick_profile_target_rows(resolved$asset_mappings,"asset_id"),now_utc
  ))
  if(!is.list(value)||!is.list(value$public_profile)||!is.list(value$trusted_profile)) .data_activity_quick_abort("data_activity_quick_import_adapter_failed")
  c(value$public_profile,list(profile_saved=TRUE))
}

data_activity_quick_mapping_profiles_v1 <- function(center,context) {
  .data_activity_quick_check(center);.data_activity_quick_context(context)
  value<-.data_activity_quick_call(function()center$adapter$profile_list(context))
  if(!is.list(value)||!is.list(value$public_list)||!is.list(value$trusted_list)||!is.list(value$public_list$profiles)||!is.list(value$trusted_list$profile_refs)||length(value$public_list$profiles)!=length(value$trusted_list$profile_refs)) .data_activity_quick_abort("data_activity_quick_import_adapter_failed")
  rm(list=ls(center$profile_entries,all.names=TRUE),envir=center$profile_entries)
  rows<-vector("list",length(value$public_list$profiles))
  for(index in seq_along(rows)){
    center$profile_sequence<-center$profile_sequence+1L;handle<-sprintf("activity_mapping_profile_%04d",center$profile_sequence)
    assign(handle,value$trusted_list$profile_refs[[index]],envir=center$profile_entries)
    rows[[index]]<-c(value$public_list$profiles[[index]],list(profile_handle=handle))
  }
  list(status=value$public_list$status,profile_count=as.integer(value$public_list$profile_count),profiles=rows,canonical_write=FALSE,path_exposed=FALSE,browser_internal_id_exposed=FALSE,fingerprint_exposed=FALSE)
}

.data_activity_quick_profile_ref_for_id <- function(selection,area,identifier) {
  values<-selection[[area]]$ref_by_id
  if(!is.character(identifier)||length(identifier)!=1L||is.na(identifier)||!identifier%in%names(values)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  value<-unname(values[[identifier]])
  if(!is.character(value)||length(value)!=1L||is.na(value)||!nzchar(value)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  value
}

data_activity_quick_mapping_profile_load_v1 <- function(center,context,profile_handle) {
  .data_activity_quick_check(center);.data_activity_quick_context(context)
  if(!is.character(profile_handle)||length(profile_handle)!=1L||is.na(profile_handle)||!exists(profile_handle,envir=center$profile_entries,inherits=FALSE)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  value<-.data_activity_quick_call(function()center$adapter$profile_read(context,get(profile_handle,envir=center$profile_entries,inherits=FALSE)))
  if(!is.list(value)||!is.list(value$public_profile)||!is.list(value$trusted_profile)) .data_activity_quick_abort("data_activity_quick_import_adapter_failed")
  trusted<-value$trusted_profile;selection<-.data_asset_activity_selection(center$activity_editor,context)
  mappings<-function(rows,area)lapply(rows,function(row)list(source_key=row$source_key,target_ref=.data_activity_quick_profile_ref_for_id(selection,area,row$target_id)))
  profile<-new_data_activity_quick_mapping_profile_v1(
    context,
    .data_activity_quick_profile_ref_for_id(selection,"portfolios",trusted$default_portfolio_id),
    .data_activity_quick_profile_ref_for_id(selection,"accounts",trusted$default_account_id),
    portfolio_mappings=mappings(trusted$portfolio_mappings,"portfolios"),
    account_mappings=mappings(trusted$account_mappings,"accounts"),
    asset_mappings=mappings(trusted$asset_mappings,"assets")
  )
  list(status="loaded",profile=profile,public_profile=value$public_profile,canonical_write=FALSE,path_exposed=FALSE,browser_internal_id_exposed=FALSE,fingerprint_exposed=FALSE)
}

.data_activity_quick_mapping_keys <- function(entries) if(length(entries))vapply(entries,`[[`,character(1L),"source_key")else character()

.data_activity_quick_mapping_target <- function(entries,key) {
  if(!nzchar(key))return(NULL)
  matches<-Filter(function(entry)identical(entry$source_key,key),entries)
  if(length(matches)!=1L)return(NULL)
  matches[[1L]]$target
}

.data_activity_quick_mapping_complete <- function(requirements,entries) setequal(
  if(length(requirements))vapply(requirements,`[[`,character(1L),"source_key")else character(),
  .data_activity_quick_mapping_keys(entries)
)

.data_activity_quick_row_mapping <- function(profile,row) {
  key<-function(field).data_activity_quick_text(row[[field]])
  explicit<-identical(profile$mapping_mode,"explicit_key_mapping")
  portfolio<-if(nzchar(key("portfolio_key"))&&explicit).data_activity_quick_mapping_target(profile$portfolio_mappings,key("portfolio_key"))else profile$default_portfolio
  account<-if(nzchar(key("account_key"))&&explicit).data_activity_quick_mapping_target(profile$account_mappings,key("account_key"))else profile$default_account
  asset<-if(explicit).data_activity_quick_mapping_target(profile$asset_mappings,key("asset_key"))else profile$default_asset
  related<-if(explicit).data_activity_quick_mapping_target(profile$account_mappings,key("related_account_key"))else NULL
  source_asset<-if(explicit).data_activity_quick_mapping_target(profile$asset_mappings,key("source_asset_key"))else NULL
  list(portfolio=portfolio,account=account,asset=asset,related_account=related,source_asset=source_asset)
}

.data_activity_quick_event <- function(center,context,row,mapping) {
  keys<-c("event_type","account_ref","related_account_ref","asset_ref","source_asset_ref","event_time_evidence","local_date","local_time","time_zone","effective_at_utc","original_acquired_time_evidence","original_acquired_local_date","original_acquired_local_time","original_acquired_time_zone","original_acquired_at_utc","amount_input_mode","basis_evidence_mode","quantity_decimal","eligible_quantity_decimal","unit_price_decimal","gross_amount_decimal","monetary_fee_decimal","asset_fee_quantity_decimal","provided_basis_decimal","movement_context_code")
  event<-setNames(vector("list",length(keys)),keys)
  if(is.null(mapping$account))event["account_ref"]<-NULL else event$account_ref<-mapping$account$account_id
  if(is.null(mapping$asset))event["asset_ref"]<-NULL else event$asset_ref<-mapping$asset$asset_id
  event_type<-.data_activity_quick_value(row$event_type)
  if(is.null(event_type))event["event_type"]<-NULL else event$event_type<-event_type
  if(identical(event_type,"transfer")){
    if(is.null(mapping$related_account))event["related_account_ref"]<-NULL else event$related_account_ref<-mapping$related_account$account_id
  }else event["related_account_ref"]<-list(NULL)
  if(identical(event_type,"stock_dividend")){
    if(is.null(mapping$source_asset))event["source_asset_ref"]<-NULL else event$source_asset_ref<-mapping$source_asset$asset_id
  }else event["source_asset_ref"]<-list(NULL)
  mode<-.data_activity_quick_value(row$event_time_evidence)
  if(is.null(mode))event[c("event_time_evidence","local_date","local_time","time_zone","effective_at_utc")]<-NULL else{
    event$event_time_evidence<-mode;event$local_date<-.data_activity_quick_value(row$local_date);event$time_zone<-.data_activity_quick_value(row$time_zone)
    if(identical(mode,"exact")&&!is.null(event$local_date)&&nzchar(.data_activity_quick_text(row$local_time))&&!is.null(event$time_zone)){
      event$local_time<-row$local_time;event$effective_at_utc<-.data_activity_quick_call(function()center$adapter$resolve_time(context,row$local_date,row$local_time,row$time_zone))$effective_at_utc
    }else if(identical(mode,"date_only")){event["local_time"]<-list(NULL);event["effective_at_utc"]<-list(NULL)}else event[c("local_time","effective_at_utc")]<-NULL
  }
  original<-.data_activity_quick_value(row$original_acquired_time_evidence)
  if(is.null(original))event[c("original_acquired_time_evidence","original_acquired_local_date","original_acquired_local_time","original_acquired_time_zone","original_acquired_at_utc")]<-NULL else{
    event$original_acquired_time_evidence<-original
    if(identical(original,"not_applicable")){
      for(field in c("original_acquired_local_date","original_acquired_local_time","original_acquired_time_zone","original_acquired_at_utc"))event[field]<-list(NULL)
    }else{
      event$original_acquired_local_date<-.data_activity_quick_value(row$original_acquired_local_date);event$original_acquired_time_zone<-.data_activity_quick_value(row$original_acquired_time_zone)
      if(identical(original,"exact")&&!is.null(event$original_acquired_local_date)&&nzchar(.data_activity_quick_text(row$original_acquired_local_time))&&!is.null(event$original_acquired_time_zone)){
        event$original_acquired_local_time<-row$original_acquired_local_time;event$original_acquired_at_utc<-.data_activity_quick_call(function()center$adapter$resolve_time(context,row$original_acquired_local_date,row$original_acquired_local_time,row$original_acquired_time_zone))$effective_at_utc
      }else if(identical(original,"exact")){
        if(nzchar(.data_activity_quick_text(row$original_acquired_local_time)))event$original_acquired_local_time<-row$original_acquired_local_time else event["original_acquired_local_time"]<-NULL
        event["original_acquired_at_utc"]<-NULL
      }else{event["original_acquired_local_time"]<-list(NULL);event["original_acquired_at_utc"]<-list(NULL)}
    }
  }
  for(field in c("amount_input_mode","basis_evidence_mode","quantity_decimal","eligible_quantity_decimal","unit_price_decimal","gross_amount_decimal","monetary_fee_decimal","asset_fee_quantity_decimal","provided_basis_decimal","movement_context_code")){
    value<-.data_activity_quick_value(row[[field]]);if(!is.null(value))event[[field]]<-value
  }
  amount_mode<-.data_activity_quick_value(row$amount_input_mode);basis_mode<-.data_activity_quick_value(row$basis_evidence_mode)
  required<-c("account_ref","asset_ref","amount_input_mode","basis_evidence_mode","movement_context_code","original_acquired_time_evidence")
  if(isTRUE(event_type%in%c("buy","sell","stock_dividend","reward","deposit","withdrawal","transfer")))required<-c(required,"quantity_decimal")
  if(identical(amount_mode,"quantity_unit_price"))required<-c(required,"unit_price_decimal",if(identical(event_type,"dividend"))"eligible_quantity_decimal"else character())
  if(identical(amount_mode,"gross_total"))required<-c(required,"gross_amount_decimal")
  if(identical(basis_mode,"provided_basis"))required<-c(required,"provided_basis_decimal")
  if(identical(event_type,"stock_dividend"))required<-c(required,"source_asset_ref")
  if(identical(event_type,"transfer"))required<-c(required,"related_account_ref")
  for(field in unique(required))if(is.null(event[[field]]))event[field]<-NULL
  if(nzchar(.data_activity_quick_text(row$unclassified_fee_decimal))){
    if(nzchar(.data_activity_quick_text(row$monetary_fee_decimal))||nzchar(.data_activity_quick_text(row$asset_fee_quantity_decimal))) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
    event[c("monetary_fee_decimal","asset_fee_quantity_decimal")]<-NULL
  }
  event
}

.data_activity_quick_valuation_evidence <- function(row,mapping) {
  event_type<-.data_activity_quick_text(row$event_type)
  relevant<-event_type%in%c("reward","stock_dividend","deposit")
  adapter<-list(adapter_id="redundant_asset_activity_csv_v1",adapter_version="1.0.0")
  if(!relevant)return(c(adapter,list(valuation_origin="not_applicable",source_value_mode="none",price_currency=NULL,source_unit_price_decimal=NULL,source_fiat_total_decimal=NULL)))
  currency<-.data_activity_quick_text(row$price_currency)
  if(!nzchar(currency)&&!is.null(mapping$portfolio))currency<-.data_activity_quick_text(mapping$portfolio$base_currency)
  if(!grepl("^[A-Z]{3}$",currency)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  unit<-.data_activity_quick_text(row$unit_price_decimal)
  total<-.data_activity_quick_text(row$gross_amount_decimal)
  if(!nzchar(total))total<-.data_activity_quick_text(row$provided_basis_decimal)
  if(nzchar(unit)&&nzchar(total)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  if(nzchar(unit))return(c(adapter,list(valuation_origin="source_provided",source_value_mode="unit_price",price_currency=currency,source_unit_price_decimal=unit,source_fiat_total_decimal=NULL)))
  if(nzchar(total))return(c(adapter,list(valuation_origin="source_provided",source_value_mode="fiat_total",price_currency=currency,source_unit_price_decimal=NULL,source_fiat_total_decimal=total)))
  c(adapter,list(valuation_origin="source_missing",source_value_mode="none",price_currency=currency,source_unit_price_decimal=NULL,source_fiat_total_decimal=NULL))
}

data_activity_quick_prepare_v1 <- function(center,context,profile,now_utc) {
  .data_activity_quick_check(center);.data_activity_quick_context(context)
  if(is.null(center$inspection)||is.null(center$requirements)) .data_activity_quick_abort("data_activity_quick_import_source_required")
  resolved<-.data_activity_quick_profile(center,context,profile)
  entries<-lapply(seq_along(center$inspection$trusted_rows),function(index)list(source_row_ordinal=as.integer(index),row=center$inspection$trusted_rows[[index]]))
  entries<-Filter(function(entry)identical(entry$row$row_kind,"activity"),entries)
  rows<-lapply(entries,`[[`,"row")
  if(center$inspection$public_inspection$unknown_column_count>0L||center$inspection$public_inspection$blocked_row_count>0L||!length(rows)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  fee_conflict<-any(vapply(rows,function(row)nzchar(.data_activity_quick_text(row$unclassified_fee_decimal))&&(nzchar(.data_activity_quick_text(row$monetary_fee_decimal))||nzchar(.data_activity_quick_text(row$asset_fee_quantity_decimal))),logical(1L)))
  if(fee_conflict) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  if(identical(resolved$mapping_mode,"single_default")){
    primary_assets<-unique(vapply(rows,function(row)row$asset_key,character(1L)))
    primary_accounts<-unique(Filter(nzchar,vapply(rows,function(row)row$account_key,character(1L))))
    primary_portfolios<-unique(Filter(nzchar,vapply(rows,function(row)row$portfolio_key,character(1L))))
    if(length(primary_assets)>1L||length(primary_accounts)>1L||length(primary_portfolios)>1L) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  }else if(!.data_activity_quick_mapping_complete(center$requirements$portfolios,resolved$portfolio_mappings)||!.data_activity_quick_mapping_complete(center$requirements$accounts,resolved$account_mappings)||!.data_activity_quick_mapping_complete(center$requirements$assets,resolved$asset_mappings)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
  prepared<-vector("list",length(entries))
  for(index in seq_along(entries)){
    row<-entries[[index]]$row;mapping<-.data_activity_quick_row_mapping(resolved,row)
    if(is.null(mapping$portfolio)) .data_activity_quick_abort("data_activity_quick_import_mapping_required")
    event<-.data_activity_quick_event(center,context,row,mapping)
    fee<-.data_activity_quick_value(row$unclassified_fee_decimal)
    source_binding<-list(source_fingerprint=center$inspection$source_fingerprint,source_row_ordinal=entries[[index]]$source_row_ordinal,source_row_key=row$row_key)
    source_auxiliary<-list(
      unclassified_fee_decimal=fee,
      unclassified_fee_resolution=if(is.null(fee))"not_present"else"unresolved",
      valuation_evidence=.data_activity_quick_valuation_evidence(row,mapping)
    )
    draft<-data_activity_draft_create_or_reuse_tolerant_csv_v1(center$draft_center,context,mapping$portfolio$portfolio_id,event,source_binding,source_auxiliary,now_utc)
    if(identical(draft$status,"committed")){
      validated<-draft;validation_status<-"already_committed"
    }else if(identical(draft$status,"applying")){
      validated<-draft;validation_status<-"applying"
    }else{
      validated<-data_activity_draft_validate_v1(center$draft_center,context,draft$draft_handle,now_utc);validation_status<-validated$validation_status
    }
    prepared[[index]]<-list(
      draft_handle=draft$draft_handle,source_row_ordinal=entries[[index]]$source_row_ordinal,
      source_asset_key=row$asset_key,source_account_key=row$account_key,
      validation_status=validation_status,
      missing_field_count=as.integer(length(validated$missing_fields)),issue_codes=validated$issue_codes,
      unclassified_fee_status=validated$unclassified_fee_summary$status,
      valuation_origin=validated$valuation_summary$origin,
      valuation_status=validated$valuation_summary$lifecycle,
      draft_created=isTRUE(draft$created_new),draft_reused=isTRUE(draft$reused_existing)
    )
  }
  center$prepared<-prepared;statuses<-vapply(prepared,`[[`,character(1L),"validation_status")
  list(
    status=if(any(statuses=="applying"))"recovery_required"else if(any(statuses=="blocked"))"blocked"else if(any(statuses=="needs_input"))"needs_input"else if(all(statuses=="already_committed"))"already_prepared"else"ready",
    row_count=as.integer(length(prepared)),ready_row_count=as.integer(sum(statuses=="ready")),
    needs_input_row_count=as.integer(sum(statuses=="needs_input")),blocked_row_count=as.integer(sum(statuses=="blocked")),
    applying_row_count=as.integer(sum(statuses=="applying")),already_committed_draft_count=as.integer(sum(statuses=="already_committed")),
    created_draft_count=as.integer(sum(vapply(prepared,`[[`,logical(1L),"draft_created"))),reused_draft_count=as.integer(sum(vapply(prepared,`[[`,logical(1L),"draft_reused"))),
    rows=lapply(prepared,function(row)row[c("source_row_ordinal","source_asset_key","source_account_key","validation_status","missing_field_count","issue_codes","unclassified_fee_status","valuation_origin","valuation_status","draft_created","draft_reused")]),
    default_account_applied=identical(resolved$mapping_mode,"single_default")||any(!nzchar(vapply(rows,function(row)row$account_key,character(1L)))),
    mapping_mode=resolved$mapping_mode,profile_role="desktop_owner",canonical_write=FALSE,
    path_exposed=FALSE,browser_internal_id_exposed=FALSE,fingerprint_exposed=FALSE
  )
}

data_activity_quick_import_ready_v1 <- function(center,context,confirmed,now_utc) {
  .data_activity_quick_check(center);.data_activity_quick_context(context)
  if(is.null(center$prepared)) .data_activity_quick_abort("data_activity_quick_import_prepare_required")
  if(!isTRUE(confirmed)) .data_activity_quick_abort("data_activity_quick_import_confirmation_required")
  ready_indexes<-which(vapply(center$prepared,function(row)identical(row$validation_status,"ready"),logical(1L)))
  receipts<-list();base<-as.POSIXct(now_utc,format="%Y-%m-%dT%H:%M:%SZ",tz="UTC")
  if(is.na(base)) .data_activity_quick_abort("data_activity_quick_import_confirmation_required")
  for(position in seq_along(ready_indexes)){
    row_index<-ready_indexes[[position]];at<-format(base+position-1L,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
    refreshed<-data_activity_draft_validate_v1(center$draft_center,context,center$prepared[[row_index]]$draft_handle,at)
    center$prepared[[row_index]]$validation_status<-refreshed$validation_status
    center$prepared[[row_index]]$missing_field_count<-as.integer(length(refreshed$missing_fields))
    center$prepared[[row_index]]$issue_codes<-refreshed$issue_codes
    if(!identical(refreshed$validation_status,"ready"))next
    invisible(data_activity_draft_confirm_v1(center$draft_center,context,center$prepared[[row_index]]$draft_handle,at))
    receipts[[length(receipts)+1L]]<-data_activity_draft_execute_v1(center$draft_center,context,center$prepared[[row_index]]$draft_handle,at)
    center$prepared[[row_index]]$validation_status<-"committed"
  }
  already_committed<-sum(vapply(receipts,function(receipt)identical(receipt$status,"already_committed"),logical(1L)))
  result<-list(
    status="completed_ready_rows",ready_row_count=as.integer(length(ready_indexes)),committed_row_count=as.integer(length(receipts)),
    created_row_count=as.integer(length(receipts)-already_committed),already_committed_row_count=as.integer(already_committed),
    deduplicated_row_count=as.integer(sum(vapply(center$prepared,function(row)identical(row$validation_status,"already_committed"),logical(1L)))),
    needs_input_row_count=as.integer(sum(vapply(center$prepared,function(row)identical(row$validation_status,"needs_input"),logical(1L)))),
    blocked_row_count=as.integer(sum(vapply(center$prepared,function(row)identical(row$validation_status,"blocked"),logical(1L)))),
    applying_row_count=as.integer(sum(vapply(center$prepared,function(row)identical(row$validation_status,"applying"),logical(1L)))),
    cash_posting_count=0L,provider_access=FALSE,network_access=FALSE,path_exposed=FALSE,
    browser_internal_id_exposed=FALSE,fingerprint_exposed=FALSE
  )
  center$prepared<-NULL
  result
}
